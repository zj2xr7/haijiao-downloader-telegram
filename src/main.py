"""
Main application startup entrypoint.
"""
import os
import sys
from pathlib import Path

# Ensure project root directory is added to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
from src.config import settings, load_settings
from src.utils.logger import logger
from src.utils.http_client import http_client
from src.core.resolver import DomainResolver
from src.core.crawler import HaijiaoCrawler
from src.core.decryptor import MediaDecryptor
from src.core.renderer import MarkdownRenderer
from src.core.disk_guard import DiskGuard
from src.core.uploader import RcloneUploader
from src.core.pipeline import PipelineManager
from src.bot.bot_app import create_bot_and_dispatcher, setup_bot_commands


async def main():
    """Initializes all services and starts Telegram long polling."""
    # Reload settings in case config path was passed via args or env
    current_settings = load_settings()

    logger.info("=========================================================")
    logger.info("   🚀 Haijiao Downloader Telegram Bot starting up...    ")
    logger.info("=========================================================")
    
    if not current_settings.BOT_TOKEN:
        logger.error("FATAL: bot.token is empty! Please configure bot.token in config.yaml.")
        sys.exit(1)

    logger.info(f"Allowed User IDs: {current_settings.allowed_user_id_list or 'ALL (Open)'}")
    logger.info(f"Publish Page URL: {current_settings.PUBLISH_PAGE_URL}")
    logger.info(f"Disk Guard Threshold: {current_settings.MIN_FREE_DISK_GB} GB")
    logger.info(f"Rclone Remote Destination: {current_settings.RCLONE_REMOTE_DEST}")
    logger.info(f"OpenList Base URL: {current_settings.OPENLIST_BASE_URL}")

    # 1. Instantiate Core Engine Components
    resolver = DomainResolver(settings=current_settings, http_cli=http_client)
    crawler = HaijiaoCrawler(settings=current_settings, resolver=resolver, http_cli=http_client)
    decryptor = MediaDecryptor(settings=current_settings, http_cli=http_client)
    renderer = MarkdownRenderer()
    disk_guard = DiskGuard(settings=current_settings)
    uploader = RcloneUploader(settings=current_settings, disk_guard=disk_guard)

    pipeline = PipelineManager(
        settings=current_settings,
        crawler=crawler,
        decryptor=decryptor,
        renderer=renderer,
        disk_guard=disk_guard,
        uploader=uploader
    )

    # 2. Wire and Initialize Telegram Bot
    bot, dp = create_bot_and_dispatcher(settings=current_settings, pipeline=pipeline)

    # 3. Register Slash Command Menu in Telegram UI
    await setup_bot_commands(bot)

    logger.info("Connecting to Telegram Bot API & starting polling dispatcher...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("Shutting down... Closing HTTP connection pool.")
        await http_client.close()
        await bot.session.close()
        logger.info("Shutdown completed.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Process terminated by user.")
