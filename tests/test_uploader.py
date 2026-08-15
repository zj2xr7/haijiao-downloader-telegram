"""
Tests for RcloneUploader.
"""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from src.core.uploader import RcloneUploader
from src.config import Settings


def test_openlist_url_generation():
    settings = Settings(
        BOT_TOKEN="fake",
        ALLOWED_USER_IDS="1",
        OPENLIST_BASE_URL="https://pan.example.com",
        OPENLIST_MOUNT_PATH="/Media/Haijiao"
    )
    uploader = RcloneUploader(settings=settings)
    
    author_folder = "Alice_u123"
    post_folder = "[9988] 精彩 排版 测试"
    
    url = uploader.get_openlist_url(author_folder, post_folder)
    assert url.startswith("https://pan.example.com/Media/Haijiao/Alice_u123/")
    assert "%20" in url or "精彩" in url


@pytest.mark.asyncio
async def test_upload_and_cleanup_with_local_destination(tmp_path):
    dest_dir = tmp_path / "remote_cloud"
    dest_dir.mkdir()
    
    settings = Settings(
        BOT_TOKEN="fake",
        ALLOWED_USER_IDS="1",
        RCLONE_REMOTE_DEST=str(dest_dir)
    )
    uploader = RcloneUploader(settings=settings)
    
    source_dir = tmp_path / "local_post"
    source_dir.mkdir()
    (source_dir / "post.md").write_text("# Hello World", encoding="utf-8")
    
    success, err = await uploader.upload_and_cleanup(source_dir, "author_1/post_1")
    assert success is True
    # Verify local source dir was cleaned up
    assert not source_dir.exists()
    # Verify file was copied to destination
    copied_md = dest_dir / "author_1" / "post_1" / "post.md"
    assert copied_md.exists()
    assert copied_md.read_text(encoding="utf-8") == "# Hello World"
