"""
Download task handlers for single posts and author batches.
"""
import re
import asyncio
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
                await message.answer("ℹ️ 请在 /dl 后附加帖子或作者链接，例如：`/dl https://.../post/1234`")
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
            f"🚀 **作者 [{author_id}] 批量下载任务已启动！**\n"
            f"📑 正在下载第 `{range_str}` 页帖子...\n"
            f"⚡ 下载和上传将在后台全自动进行，完成后将发送汇总链接。",
            parse_mode="Markdown"
        )

        asyncio.create_task(run_author_batch_background(callback.message, author_id, pages, pipeline))

    @router.callback_query(F.data.startswith("author_custom:"))
    async def handle_author_custom_page(callback: CallbackQuery, state: FSMContext):
        author_id = callback.data.split(":")[1]
        await state.set_state(AuthorDownloadState.waiting_for_custom_pages)
        await state.update_data(author_id=author_id)

        await callback.message.edit_text(
            f"✏️ **请输入作者 [{author_id}] 需要下载的页码范围**\n\n"
            f"示例格式：\n"
            f"• `1` (仅第 1 页)\n"
            f"• `1-3` (第 1 到 3 页)\n"
            f"• `2,4,6` (指定第 2、4、6 页)\n\n"
            f"请直接回复消息输入：",
            parse_mode="Markdown"
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
            f"🚀 **作者 [{author_id}] 自定义页码 `{pages}` 批量任务已启动！**\n"
            f"后台正在流水线作业中...",
            parse_mode="Markdown"
        )
        asyncio.create_task(run_author_batch_background(message, author_id, pages, pipeline))

    @router.callback_query(F.data == "cancel_action")
    async def handle_cancel_action(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.message.edit_text("❌ 操作已取消。")
        await callback.answer()

    return router


async def start_single_post_download(message: Message, post_id: str, pipeline: PipelineManager):
    """Executes single post download with live Telegram message updates."""
    status_msg = await message.answer(f"⏳ **[Post {post_id}]** 任务已接收，正在排队解析...", parse_mode="Markdown")
    last_update_text = ""

    async def update_progress(pid: str, text: str):
        nonlocal last_update_text
        if text != last_update_text:
            last_update_text = text
            try:
                await status_msg.edit_text(f"⏳ **[Post {pid}]**\n{text}", parse_mode="Markdown")
            except Exception:
                pass

    result = await pipeline.process_single_post(post_id, progress_callback=update_progress)

    if result.stage == TaskStage.COMPLETED:
        summary_text = (
            "✅ **下载并上传完成！**\n\n"
            f"📖 **标题**: {result.title}\n"
            f"👤 **作者**: {result.author_name}\n"
            f"🖼️ **图片**: {result.downloaded_images} 张 | 🎬 **视频**: {result.downloaded_videos} 部\n"
            f"⏱️ **耗时**: {result.elapsed_seconds} 秒\n\n"
            f"🔗 **已归档至 OneDrive 并生成 OpenList 索引**"
        )
        kb = build_openlist_button(result.openlist_url) if result.openlist_url else None
        await status_msg.edit_text(summary_text, reply_markup=kb, parse_mode="Markdown")
    else:
        fail_text = (
            f"❌ **处理失败 [Post {post_id}]**\n\n"
            f"⚠️ **原因**: {result.error_message or '未知错误'}"
        )
        await status_msg.edit_text(fail_text, parse_mode="Markdown")


async def start_author_interaction(message: Message, author_id: str, crawler: HaijiaoCrawler, state: FSMContext):
    """Fetches author profile and presents the interactive page selector."""
    loading_msg = await message.answer(f"🔍 正在查询作者 `{author_id}` 的主页信息...", parse_mode="Markdown")
    summary = await crawler.fetch_author_summary(author_id)

    author_card = (
        f"👤 **作者主页**: **{summary.author_name}** (ID: `{summary.author_id}`)\n"
        f"📊 **估算作品数**: 约 {summary.total_posts} 篇 | 共 {summary.total_pages} 页\n\n"
        f"👇 **请选择需要下载的页码范围**："
    )
    kb = build_author_pages_keyboard(author_id, summary.total_pages)
    await loading_msg.edit_text(author_card, reply_markup=kb, parse_mode="Markdown")


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
                f"✅ **[作者批量完成]**\n"
                f"📖 `{result.title}` (编号: {result.post_id})\n"
                f"🖼️ 图片: {result.downloaded_images} | 🎬 视频: {result.downloaded_videos}",
                reply_markup=kb,
                parse_mode="Markdown"
            )
        else:
            total_failed += 1

    await message.answer(
        f"🎉 **作者 [{author_id}] 批量任务全部结束！**\n\n"
        f"✅ 成功完成: {total_completed} 篇\n"
        f"❌ 失败: {total_failed} 篇",
        parse_mode="Markdown"
    )
