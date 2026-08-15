"""
Tests for configuration and models.
"""
import pytest
from pathlib import Path
from src.config import Settings, load_settings
from src.models import PostDetail, MediaItem, ContentSegment, TaskStage, TaskResult


def test_settings_from_yaml(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
bot:
  token: "test_bot_token_yaml_123"
  allowed_user_ids:
    - 111
    - 222
    - 333
network:
  publish_page_url: "https://hjw2026.com"
  domain_refresh_interval_hours: 8
  request_timeout_seconds: 45
  max_download_concurrency: 3
storage:
  temp_download_dir: "./custom_downloads"
  min_free_disk_gb: 3.5
rclone:
  config_path: "/root/.config/rclone/rclone.conf"
  remote_dest: "onedrive:Media/Custom"
  max_upload_concurrency: 4
openlist:
  base_url: "https://pan.custom.com"
  mount_path: "/Media/Custom"
""", encoding="utf-8")

    settings = load_settings(config_path=str(config_file))
    assert settings.BOT_TOKEN == "test_bot_token_yaml_123"
    assert settings.allowed_user_id_list == [111, 222, 333]
    assert settings.MIN_FREE_DISK_GB == 3.5
    assert settings.PUBLISH_PAGE_URL == "https://hjw2026.com"
    assert settings.DOMAIN_REFRESH_INTERVAL_HOURS == 8
    assert settings.REQUEST_TIMEOUT_SECONDS == 45
    assert settings.MAX_DOWNLOAD_CONCURRENCY == 3
    assert settings.RCLONE_REMOTE_DEST == "onedrive:Media/Custom"
    assert settings.MAX_UPLOAD_CONCURRENCY == 4
    assert settings.OPENLIST_BASE_URL == "https://pan.custom.com"
    assert settings.OPENLIST_MOUNT_PATH == "/Media/Custom"


def test_settings_kwargs_override():
    settings = Settings(
        BOT_TOKEN="direct_token_999",
        ALLOWED_USER_IDS="888,999",
        MIN_FREE_DISK_GB=4.0
    )
    assert settings.BOT_TOKEN == "direct_token_999"
    assert settings.allowed_user_id_list == [888, 999]
    assert settings.MIN_FREE_DISK_GB == 4.0


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
