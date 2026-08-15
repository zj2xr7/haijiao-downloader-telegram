"""
Adaptive disk space monitor and download gating mechanism for small VPS.
"""
import shutil
import asyncio
from pathlib import Path
from typing import Optional

from src.config import Settings, settings as default_settings
from src.utils.logger import logger


class DiskGuard:
    """Monitors remaining VPS disk capacity and gates downloads to prevent running out of disk space."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        watch_dir: Optional[Path] = None,
        max_concurrency: Optional[int] = None
    ):
        self.settings = settings or default_settings
        self.watch_dir = watch_dir or self.settings.temp_download_path
        concurrency = max_concurrency or self.settings.MAX_DOWNLOAD_CONCURRENCY
        self.semaphore = asyncio.Semaphore(concurrency)
        self._space_freed_event = asyncio.Event()
        self._space_freed_event.set()

    def get_free_space_gb(self) -> float:
        """Returns the current free disk space in Gigabytes for the watch directory."""
        try:
            self.watch_dir.mkdir(parents=True, exist_ok=True)
            usage = shutil.disk_usage(str(self.watch_dir))
            free_gb = usage.free / (1024 ** 3)
            return round(free_gb, 2)
        except Exception as exc:
            logger.error(f"Error checking disk usage at {self.watch_dir}: {exc}")
            return 999.0

    async def can_download_now(self) -> bool:
        """Checks if current free space meets the required threshold."""
        free_gb = self.get_free_space_gb()
        return free_gb >= self.settings.MIN_FREE_DISK_GB

    async def acquire_download_slot(self) -> None:
        """
        Acquires a concurrency slot. If free space is below MIN_FREE_DISK_GB,
        suspends execution until disk space is released by uploading jobs.
        """
        await self.semaphore.acquire()
        
        while True:
            free_gb = self.get_free_space_gb()
            if free_gb >= self.settings.MIN_FREE_DISK_GB:
                logger.debug(f"DiskGuard: Free space is {free_gb} GB (Threshold: {self.settings.MIN_FREE_DISK_GB} GB). Permitted.")
                break
            
            logger.warning(
                f"DiskGuard: Low disk space! {free_gb} GB available (Required: {self.settings.MIN_FREE_DISK_GB} GB). "
                f"Pausing new download until uploads finish and free up space..."
            )
            self._space_freed_event.clear()
            # Wait until space is freed or timeout 10s to recheck
            try:
                await asyncio.wait_for(self._space_freed_event.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                pass

    def release_download_slot(self) -> None:
        """Releases the download concurrency slot."""
        self.semaphore.release()

    def notify_disk_freed(self) -> None:
        """Wakes up waiting download jobs after uploaded files have been deleted."""
        free_gb = self.get_free_space_gb()
        logger.info(f"DiskGuard: Space freed notification received. Current free space: {free_gb} GB.")
        self._space_freed_event.set()
