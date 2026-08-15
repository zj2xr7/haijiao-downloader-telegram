"""
Main application startup entrypoint.
"""
import sys
import asyncio
from src.config import settings
from src.utils.logger import logger
from src.utils.http_client import http_client
from src.core.resolver import DomainResolver
from src.core.crawler import HaijiaoCrawler
from src.core.decryptor import MediaDecryptor
from src.core.renderer import MarkdownRenderer
from src.core.disk_guard import DiskGuard
from src.core.uploader import RcloneUploader
from src.core.pipeline import PipelineManager
from src.bot.bot_app import create_bot_and_dispatcher


async def main():
    """Initializes all services and starts Telegram long polling."""
    logger.info("=========================================================")
    logger.info("   🚀 Haijiao Downloader Telegram Bot starting up...    ")
    logger.info("=========================================================")
    
    if not settings.BOT_TOKEN:
        logger.error("FATAL: BOT_TOKEN is empty! Please configure BOT_TOKEN in .env or environment variables.")
        sys.exit(1)

    logger.info(f"Allowed User IDs: {settings.allowed_user_id_list or 'ALL (Open)'}")
    logger.info(f"Publish Page URL: {settings.PUBLISH_PAGE_URL}")
    logger.info(f"Disk Guard Threshold: {settings.MIN_FREE_DISK_GB} GB")
    logger.info(f"Rclone Remote Destination: {settings.RCLONE_REMOTE_DEST}")
    logger.info(f"OpenList Base URL: {settings.OPENLIST_BASE_URL}")

    # 1. Instantiate Core Engine Components
    resolver = DomainResolver(settings=settings, http_cli=http_client)
    crawler = HaijiaoCrawler(settings=settings, resolver=resolver, http_cli=http_client)
    decryptor = MediaDecryptor(settings=settings, http_cli=http_client)
    renderer = MarkdownRenderer()
    disk_guard = DiskGuard(settings=settings)
    uploader = RcloneUploader(settings=settings, disk_guard=disk_guard)

    pipeline = PipelineManager(
        settings=settings,
        crawler=crawler,
        decryptor=decryptor,
        renderer=renderer,
        disk_guard=disk_guard,
        uploader=uploader
    )

    # 2. Wire and Initialize Telegram Bot
    bot, dp = create_bot_and_dispatcher(settings=settings, pipeline=pipeline)

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
