"""
Tests for DiskGuard.
"""
import pytest
from src.core.disk_guard import DiskGuard
from src.config import Settings


@pytest.mark.asyncio
async def test_disk_guard_capacity_and_slot(tmp_path):
    settings = Settings(
        BOT_TOKEN="fake",
        ALLOWED_USER_IDS="1",
        MIN_FREE_DISK_GB=0.0001,
        MAX_DOWNLOAD_CONCURRENCY=1
    )
    guard = DiskGuard(settings=settings, watch_dir=tmp_path)
    
    free_gb = guard.get_free_space_gb()
    assert free_gb > 0
    assert await guard.can_download_now() is True

    # Test acquire and release
    await guard.acquire_download_slot()
    guard.release_download_slot()

    # Test space freed event notify
    guard.notify_disk_freed()
    assert guard._space_freed_event.is_set() is True
