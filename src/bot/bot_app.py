"""
Telegram Bot Application setup, dependency injection, Dispatcher wiring and command menu registration.
"""
from typing import Tuple, Optional
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import Settings, settings as default_settings
from src.core.pipeline import PipelineManager
from src.core.crawler import HaijiaoCrawler
from src.core.disk_guard import DiskGuard
from src.core.resolver import DomainResolver
from src.bot.middlewares.auth import AuthMiddleware
from src.bot.handlers import setup_base_router, setup_download_router
from src.utils.logger import logger


async def setup_bot_commands(bot: Bot) -> None:
    """
    Registers slash commands in the Telegram client UI so the command menu pops up
    when users type '/' or click the Menu button.
    """
    commands = [
        BotCommand(command="start", description="启动机器人与功能简介"),
        BotCommand(command="status", description="查看 VPS 存储、线路与系统状态"),
        BotCommand(command="help", description="详细使用指南与支持格式"),
        BotCommand(command="dl", description="下载指定帖子或作者主页")
    ]
    try:
        await bot.set_my_commands(commands)
        logger.info("Successfully registered Telegram Bot command menu.")
    except Exception as exc:
        logger.warning(f"Failed to register Telegram bot commands: {exc}")


def create_bot_and_dispatcher(
    settings: Optional[Settings] = None,
    pipeline: Optional[PipelineManager] = None
) -> Tuple[Bot, Dispatcher]:
    """Factory creating and wiring the Bot, Dispatcher, Middlewares and Handlers."""
    cfg = settings or default_settings
    
    if not cfg.BOT_TOKEN:
        logger.warning("BOT_TOKEN is not configured! Bot cannot connect without a valid token.")

    bot = Bot(token=cfg.BOT_TOKEN or "123456:mock_token_for_tests")
    dp = Dispatcher(storage=MemoryStorage())

    # Build core dependencies if not injected
    pipe = pipeline or PipelineManager(settings=cfg)
    crawler = pipe.crawler
    disk_guard = pipe.disk_guard
    resolver = crawler.resolver

    # Register Middlewares
    auth_middleware = AuthMiddleware(settings=cfg)
    dp.message.outer_middleware(auth_middleware)
    dp.callback_query.outer_middleware(auth_middleware)

    # Provide dependencies to handlers via workflow data
    dp["settings"] = cfg
    dp["pipeline"] = pipe
    dp["crawler"] = crawler
    dp["disk_guard"] = disk_guard
    dp["resolver"] = resolver

    # Register Routers
    dp.include_router(setup_base_router())
    dp.include_router(setup_download_router())

    return bot, dp
