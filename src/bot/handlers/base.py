"""
Base bot handlers for /start, /help, and /status commands using HTML formatting.
"""
import html
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from src.config import Settings
from src.core.disk_guard import DiskGuard
from src.core.resolver import DomainResolver


def setup_base_router() -> Router:
    """Creates and configures a fresh base router."""
    router = Router(name="base_router")

    @router.message(CommandStart())
    async def cmd_start(message: Message):
        welcome_text = (
            "👋 <b>欢迎使用海角下载自动化机器人！</b>\n\n"
            "✨ <b>核心功能亮点</b>：\n"
            "• 📥 <b>单帖下载</b>：发送帖子链接或 ID，自动抓取图文排版、解密并上传至 OneDrive\n"
            "• 📚 <b>作者批量</b>：发送作者主页链接，支持交互式选择下载页码范围\n"
            "• 🛡️ <b>智能防爆盘</b>：内置 DiskGuard，边下边传，自动释放 VPS 空间\n"
            "• 📂 <b>OpenList 联动</b>：任务完成自动生成并发送 Web 直达浏览链接\n\n"
            "💡 <b>快捷操作（点击蓝色命令直接触发）</b>：\n"
            "• 直接发送海角任意链接或纯 ID\n"
            "• 点击 /status 查看 VPS 存储与线路健康状态\n"
            "• 点击 /help 查看详细使用说明\n"
            "• 点击 /dl 下载指定链接"
        )
        await message.answer(welcome_text, parse_mode="HTML")

    @router.message(Command("help"))
    async def cmd_help(message: Message):
        help_text = (
            "📖 <b>使用指南</b>\n\n"
            "1. <b>下载单篇帖子</b>：\n"
            "   直接发送帖子链接（如 <code>https://.../archives/12345/</code>）或纯数字 ID <code>12345</code>。\n\n"
            "2. <b>下载作者名下帖子</b>：\n"
            "   发送作者主页链接（如 <code>https://.../author/9988/new/</code>），Bot 将弹出分页选择按钮，点击即可开始批量下载。\n\n"
            "3. <b>系统状态查看</b>：\n"
            "   点击 /status 查看 VPS 磁盘空间、下载阈值以及当前活跃的镜像域名。\n\n"
            "4. <b>快捷命令</b>：\n"
            "   • /status - 检查运行状态\n"
            "   • /help - 帮助说明\n"
            "   • /start - 重新启动"
        )
        await message.answer(help_text, parse_mode="HTML")

    @router.message(Command("status"))
    async def cmd_status(message: Message, settings: Settings, disk_guard: DiskGuard, resolver: DomainResolver):
        free_gb = disk_guard.get_free_space_gb()
        active_domain = await resolver.get_active_domain()
        
        status_text = (
            "📊 <b>系统运行状态</b>\n\n"
            f"💾 <b>VPS 磁盘剩余</b>: <code>{free_gb} GB</code>\n"
            f"🛡️ <b>下载安全阈值</b>: <code>{settings.MIN_FREE_DISK_GB} GB</code>\n"
            f"🌐 <b>当前活跃域名</b>: <code>{html.escape(active_domain)}</code>\n"
            f"☁️ <b>云存储目标</b>: <code>{html.escape(settings.RCLONE_REMOTE_DEST)}</code>\n"
            f"📂 <b>OpenList 站点</b>: <code>{html.escape(settings.OPENLIST_BASE_URL)}</code>\n\n"
            "💡 可点击 /help 查看使用说明，或直接发送链接开启下载。"
        )
        await message.answer(status_text, parse_mode="HTML")

    return router
