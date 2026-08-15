"""
Tests for configuration and models.
"""
import pytest
from src.config import Settings
from src.models import PostDetail, MediaItem, ContentSegment, TaskStage, TaskResult


def test_settings_default_values(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test_bot_token_123")
    monkeypatch.setenv("ALLOWED_USER_IDS", "111,222,333")
    monkeypatch.setenv("MIN_FREE_DISK_GB", "3.5")
    settings = Settings()
    assert settings.BOT_TOKEN == "test_bot_token_123"
    assert settings.allowed_user_id_list == [111, 222, 333]
    assert settings.MIN_FREE_DISK_GB == 3.5
    assert settings.PUBLISH_PAGE_URL == "https://hjw2026.com"


def test_post_detail_model():
    item = MediaItem(
        media_type="image",
        remote_url="https://example.com/1.enc",
        relative_path="images/01.jpg"
    )
    post = PostDetail(
        post_id="1001",
        title="Test Post",
        author_id="u99",
        author_name="Alice",
        source_url="https://example.com/post/1001",
        content_segments=[
            ContentSegment(segment_type="text", text_content="Hello world"),
            ContentSegment(segment_type="image", media_item=item)
        ],
        total_images=1
    )
    assert post.post_id == "1001"
    assert len(post.content_segments) == 2
    assert post.content_segments[1].media_item.relative_path == "images/01.jpg"


def test_task_result_model():
    res = TaskResult(
        post_id="1001",
        title="Test Post",
        author_name="Alice",
        stage=TaskStage.COMPLETED,
        openlist_url="https://pan.example.com/Media/Haijiao/Alice_u99/[1001]%20Test%20Post/",
        downloaded_images=5,
        downloaded_videos=1
    )
    assert res.stage == TaskStage.COMPLETED
    assert res.downloaded_images == 5
