"""
Base bot handlers for /start, /help, and /status commands.
"""
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
            "👋 **欢迎使用海角下载自动化机器人！**\n\n"
            "✨ **支持功能**：\n"
            "• 📥 **单帖下载**：直接发送帖子链接或 ID，自动抓取图文排版、解密媒体并上传至 OneDrive\n"
            "• 📚 **作者批量**：发送作者主页链接，支持交互式选择下载页码范围\n"
            "• 🛡️ **智能防爆盘**：内置 DiskGuard，边下边传，自动释放 VPS 空间\n"
            "• 📂 **OpenList 联动**：任务完成自动生成并发送 Web 查看直达链接\n\n"
            "💡 **快捷操作（点击蓝色命令直接触发）**：\n"
            "• 发送海角任意帖子/作者主页链接或纯 ID\n"
            "• 点击 /status 查看 VPS 存储与线路健康状态\n"
            "• 点击 /help 查看详细使用说明\n"
            "• 点击 /dl 下载指定链接"
        )
        await message.answer(welcome_text, parse_mode="Markdown")

    @router.message(Command("help"))
    async def cmd_help(message: Message):
        help_text = (
            "📖 **使用指南**\n\n"
            "1. **下载单篇帖子**：\n"
            "   直接发送帖子链接（如 `https://.../post/details?pid=12345`）或纯数字 ID `12345`。\n\n"
            "2. **下载作者名下帖子**：\n"
            "   发送作者主页链接（如 `https://.../user/home?uid=9988`），Bot 将弹出分页选择按钮，点击即可开始批量下载。\n\n"
            "3. **系统状态查看**：\n"
            "   点击 /status 查看 VPS 磁盘空间、下载阈值以及当前活跃的镜像域名。\n\n"
            "4. **快捷命令**：\n"
            "   • /status - 检查运行状态\n"
            "   • /help - 帮助说明\n"
            "   • /start - 重新启动"
        )
        await message.answer(help_text, parse_mode="Markdown")

    @router.message(Command("status"))
    async def cmd_status(message: Message, settings: Settings, disk_guard: DiskGuard, resolver: DomainResolver):
        free_gb = disk_guard.get_free_space_gb()
        active_domain = await resolver.get_active_domain()
        
        status_text = (
            "📊 **系统运行状态**\n\n"
            f"💾 **VPS 磁盘剩余**: `{free_gb} GB`\n"
            f"🛡️ **下载安全阈值**: `{settings.MIN_FREE_DISK_GB} GB`\n"
            f"🌐 **当前活跃域名**: `{active_domain}`\n"
            f"☁️ **云存储目标**: `{settings.RCLONE_REMOTE_DEST}`\n"
            f"📂 **OpenList 站点**: `{settings.OPENLIST_BASE_URL}`\n\n"
            "💡 可点击 /help 查看使用说明，或直接发送链接开启下载。"
        )
        await message.answer(status_text, parse_mode="Markdown")

    return router
