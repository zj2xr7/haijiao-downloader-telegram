"""
Download task handlers for single posts and author batches using HTML formatting.
"""
import re
import html
import time
import asyncio
from typing import Optional
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from src.core.crawler import HaijiaoCrawler
from src.core.pipeline import PipelineManager
from src.bot.keyboards.inline import build_author_pages_keyboard, build_openlist_button
from src.models import TaskStage
from src.utils.logger import logger


class AuthorDownloadState(StatesGroup):
    """FSM states for custom page range input."""
    waiting_for_custom_pages = State()


def generate_progress_bar(percent: int, length: int = 10) -> str:
    """Generates an ASCII/Unicode progress bar like [██████░░░░]."""
    percent = max(0, min(100, percent))
    filled = int((percent / 100) * length)
    empty = length - filled
    return f"[{'█' * filled}{'░' * empty}] {percent}%"


def setup_download_router() -> Router:
    """Creates and configures a fresh download router."""
    router = Router(name="download_router")

    @router.message(Command("dl"))
    @router.message(F.text)
    async def handle_url_or_id_input(
        message: Message,
        crawler: HaijiaoCrawler,
        pipeline: PipelineManager,
        state: FSMContext
    ):
        text = message.text.strip()
        if text.startswith("/dl"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await message.answer("ℹ️ 请在 /dl 后附加帖子或作者链接，例如：<code>/dl 191635</code>", parse_mode="HTML")
                return
            text = parts[1].strip()

        # If currently in waiting_for_custom_pages state, skip URL extraction here
        current_state = await state.get_state()
        if current_state == AuthorDownloadState.waiting_for_custom_pages:
            return

        try:
            kind, target_id = crawler.extract_id_from_url(text)
        except Exception:
            if message.text.startswith("/dl"):
                await message.answer("⚠️ 无法识别输入的链接或编号，请检查后重试。")
            return

        if kind == "post":
            await start_single_post_download(message, target_id, pipeline)
        elif kind == "author":
            await start_author_interaction(message, target_id, crawler, state)

    @router.callback_query(F.data.startswith("author_dl:"))
    async def handle_author_download_callback(callback: CallbackQuery, pipeline: PipelineManager):
        parts = callback.data.split(":")
        author_id = parts[1]
        range_str = parts[2]

        try:
            start_p, end_p = map(int, range_str.split("-"))
            pages = list(range(start_p, end_p + 1))
        except Exception:
            pages = [1]

        await callback.answer(f"🚀 已启动批量任务：第 {range_str} 页", show_alert=False)
        await callback.message.edit_text(
            f"🚀 <b>作者 [{html.escape(author_id)}] 批量下载任务已启动！</b>\n\n"
            f"📑 <b>任务范围</b>: 第 <code>{html.escape(range_str)}</code> 页作品\n"
            f"⚡ 边下载边上传流水线作业中，完成后将发送汇总与 OpenList 直达卡片。",
            parse_mode="HTML"
        )

        asyncio.create_task(run_author_batch_background(callback.message, author_id, pages, pipeline))

    @router.callback_query(F.data.startswith("author_custom:"))
    async def handle_author_custom_page(callback: CallbackQuery, state: FSMContext):
        author_id = callback.data.split(":")[1]
        await state.set_state(AuthorDownloadState.waiting_for_custom_pages)
        await state.update_data(author_id=author_id)

        await callback.message.edit_text(
            f"✏️ <b>请输入作者 [{html.escape(author_id)}] 需要下载的页码范围</b>\n\n"
            f"示例格式：\n"
            f"• <code>1</code> (仅第 1 页)\n"
            f"• <code>1-3</code> (第 1 到 3 页)\n"
            f"• <code>2,4,6</code> (指定第 2、4、6 页)\n\n"
            f"请直接回复本会话：",
            parse_mode="HTML"
        )
        await callback.answer()

    @router.message(AuthorDownloadState.waiting_for_custom_pages)
    async def handle_custom_pages_input(
        message: Message,
        pipeline: PipelineManager,
        state: FSMContext
    ):
        data = await state.get_data()
        author_id = data.get("author_id")
        raw_text = message.text.strip()
        await state.clear()

        pages = []
        if "-" in raw_text:
            parts = raw_text.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                start_p, end_p = int(parts[0]), int(parts[1])
                pages = list(range(min(start_p, end_p), max(start_p, end_p) + 1))
        elif "," in raw_text or "，" in raw_text:
            sep = "," if "," in raw_text else "，"
            for p in raw_text.split(sep):
                p = p.strip()
                if p.isdigit():
                    pages.append(int(p))
        elif raw_text.isdigit():
            pages = [int(raw_text)]

        if not pages or not author_id:
            await message.answer("⚠️ 页码格式未识别，操作已取消。")
            return

        await message.answer(
            f"🚀 <b>作者 [{html.escape(author_id)}] 自定义页码 <code>{pages}</code> 批量任务已启动！</b>\n"
            f"后台流水线作业中...",
            parse_mode="HTML"
        )
        asyncio.create_task(run_author_batch_background(message, author_id, pages, pipeline))

    @router.callback_query(F.data == "cancel_action")
    async def handle_cancel_action(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.message.edit_text("❌ 操作已取消。")
        await callback.answer()

    return router


async def start_single_post_download(message: Message, post_id: str, pipeline: PipelineManager):
    """Executes single post download with rich, live Telegram HTML message updates."""
    status_msg = await message.answer(
        f"⏳ <b>[Post {html.escape(post_id)}]</b> 任务已接收，正在排队解析...",
        parse_mode="HTML"
    )
    last_update_text = ""
    last_edit_time = 0.0

    async def update_progress(
        post_id: str,
        stage_desc: str,
        title: str = "",
        author: str = "",
        stage: TaskStage = TaskStage.DOWNLOADING,
        percent: int = 0,
        media_detail: str = ""
    ):
        nonlocal last_update_text, last_edit_time
        now = time.monotonic()
        
        # Throttle Telegram message updates to avoid 429 rate limits
        if now - last_edit_time < 1.2 and percent not in (0, 100):
            return

        bar = generate_progress_bar(percent)
        free_gb = pipeline.disk_guard.get_free_space_gb()

        card_text = (
            f"⏳ <b>[Post {html.escape(post_id)}] 下载流水线作业中</b>\n\n"
            f"📖 <b>标题</b>: {html.escape(title or f'Post {post_id}')}\n"
            f"👤 <b>创作者</b>: {html.escape(author or '解析中...')}\n"
            f"📊 <b>进度</b>: <code>{bar}</code>\n"
            f"📌 <b>状态</b>: {stage_desc}\n"
            f"💾 <b>VPS 剩余</b>: <code>{free_gb} GB</code>"
        )

        if card_text != last_update_text:
            last_update_text = card_text
            last_edit_time = now
            try:
                await status_msg.edit_text(card_text, parse_mode="HTML")
            except Exception:
                pass

    result = await pipeline.process_single_post(post_id, progress_callback=update_progress)

    if result.stage == TaskStage.COMPLETED:
        summary_text = (
            "🎉 <b>下载与网盘上传全部完成！</b>\n\n"
            f"📖 <b>标题</b>: {html.escape(result.title)}\n"
            f"👤 <b>创作者</b>: {html.escape(result.author_name)}\n"
            f"🖼️ <b>图片</b>: {result.downloaded_images} 张 | 🎬 <b>视频</b>: {result.downloaded_videos} 部\n"
            f"⏱️ <b>总耗时</b>: {result.elapsed_seconds} 秒\n\n"
            f"☁️ <b>媒体已安全归档至 OneDrive 并生成 OpenList 索引</b>"
        )
        kb = build_openlist_button(result.openlist_url) if result.openlist_url else None
        try:
            await status_msg.edit_text(summary_text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await message.answer(summary_text, reply_markup=kb, parse_mode="HTML")
    else:
        err_detail = html.escape(result.error_message or "未知异常")
        fail_text = (
            f"❌ <b>处理失败 [Post {html.escape(post_id)}]</b>\n\n"
            f"⚠️ <b>原因</b>:\n<pre>{err_detail}</pre>\n\n"
            f"💡 <b>排查提示</b>:\n"
            f"• 若为 Rclone 报错，请检查 VPS 上的 <code>rclone.conf</code> 是否已配置好该 remote 节点并正确挂载。\n"
            f"• 若为网络抓取报错，Bot 将自动在后续请求中轮询切换可用镜像。"
        )
        try:
            await status_msg.edit_text(fail_text, parse_mode="HTML")
        except Exception:
            await message.answer(fail_text, parse_mode="HTML")


async def start_author_interaction(message: Message, author_id: str, crawler: HaijiaoCrawler, state: FSMContext):
    """Fetches author profile and presents the interactive page selector."""
    loading_msg = await message.answer(f"🔍 正在查询作者 <code>{html.escape(author_id)}</code> 的主页信息...", parse_mode="HTML")
    summary = await crawler.fetch_author_summary(author_id)

    author_card = (
        f"👤 <b>作者主页</b>: <b>{html.escape(summary.author_name)}</b> (ID: <code>{html.escape(summary.author_id)}</code>)\n"
        f"📊 <b>作品规模</b>: 约 {summary.total_posts} 篇 | 共 {summary.total_pages} 页\n\n"
        f"👇 <b>请选择需要下载的页码范围</b>："
    )
    kb = build_author_pages_keyboard(author_id, summary.total_pages)
    await loading_msg.edit_text(author_card, reply_markup=kb, parse_mode="HTML")


async def run_author_batch_background(
    message: Message,
    author_id: str,
    pages: list[int],
    pipeline: PipelineManager
):
    """Executes author batch in background and reports progress."""
    total_completed = 0
    total_failed = 0

    async for result in pipeline.process_author_pages(author_id, pages):
        if result.stage == TaskStage.COMPLETED:
            total_completed += 1
            kb = build_openlist_button(result.openlist_url) if result.openlist_url else None
            await message.answer(
                f"✅ <b>[作者批量完成]</b>\n"
                f"📖 <code>{html.escape(result.title)}</code> (编号: {html.escape(result.post_id)})\n"
                f"🖼️ 图片: {result.downloaded_images} | 🎬 视频: {result.downloaded_videos}",
                reply_markup=kb,
                parse_mode="HTML"
            )
        else:
            total_failed += 1

    await message.answer(
        f"🎉 <b>作者 [{html.escape(author_id)}] 批量任务全部结束！</b>\n\n"
        f"✅ <b>成功完成</b>: {total_completed} 篇\n"
        f"❌ <b>失败</b>: {total_failed} 篇",
        parse_mode="HTML"
    )
