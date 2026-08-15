"""
End-to-end integration and wiring verification tests.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from urllib.parse import unquote
import respx
import httpx

from src.config import Settings
from src.core.resolver import DomainResolver
from src.core.crawler import HaijiaoCrawler
from src.core.decryptor import MediaDecryptor
from src.core.renderer import MarkdownRenderer
from src.core.disk_guard import DiskGuard
from src.core.uploader import RcloneUploader
from src.core.pipeline import PipelineManager
from src.bot.bot_app import create_bot_and_dispatcher
from src.models import TaskStage


@pytest.mark.asyncio
async def test_full_system_wiring_and_execution_mock(tmp_path):
    temp_downloads = tmp_path / "downloads"
    cloud_dest = tmp_path / "onedrive_cloud"
    cloud_dest.mkdir()

    settings = Settings(
        BOT_TOKEN="123456:AAFakeTokenForMockTests_1234567890",
        ALLOWED_USER_IDS="111,222",
        TEMP_DOWNLOAD_DIR=str(temp_downloads),
        MIN_FREE_DISK_GB=0.0001,
        RCLONE_REMOTE_DEST=str(cloud_dest),
        OPENLIST_BASE_URL="https://pan.example.com",
        OPENLIST_MOUNT_PATH="/Media/Haijiao"
    )

    resolver = DomainResolver(settings=settings)
    resolver.get_active_domain = AsyncMock(return_value="https://mirror.haijiao.test")

    crawler = HaijiaoCrawler(settings=settings, resolver=resolver)
    decryptor = MediaDecryptor(settings=settings)
    renderer = MarkdownRenderer()
    disk_guard = DiskGuard(settings=settings, watch_dir=temp_downloads)
    uploader = RcloneUploader(settings=settings, disk_guard=disk_guard)

    pipeline = PipelineManager(
        settings=settings,
        crawler=crawler,
        decryptor=decryptor,
        renderer=renderer,
        disk_guard=disk_guard,
        uploader=uploader
    )

    # Mock HTML detail page and image download
    sample_html = """
    <html>
        <body>
            <h1 class="post-title">端到端测试文章</h1>
            <a href="/user/home?uid=777" class="author-name">测试作者</a>
            <span class="publish-time">2026-08-16 00:00:00</span>
            <div class="post-content">
                <p>这是段落一。</p>
                <img src="https://mirror.haijiao.test/images/p1.jpg" />
                <p>这是段落二。</p>
            </div>
        </body>
    </html>
    """
    valid_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 30

    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get("https://mirror.haijiao.test/post/details?pid=5566").mock(
            return_value=httpx.Response(200, text=sample_html)
        )
        respx_mock.get("https://mirror.haijiao.test/images/p1.jpg").mock(
            return_value=httpx.Response(200, content=valid_jpeg)
        )

        progress_updates = []
        async def on_progress(pid, text):
            progress_updates.append((pid, text))

        result = await pipeline.process_single_post("5566", progress_callback=on_progress)

        assert result.stage == TaskStage.COMPLETED
        assert result.post_id == "5566"
        assert result.title == "端到端测试文章"
        assert result.author_name == "测试作者"
        assert result.downloaded_images == 1
        
        # Verify OpenList URL matches decoded pattern
        decoded_url = unquote(result.openlist_url)
        assert "https://pan.example.com/Media/Haijiao/测试作者_777/[5566] 端到端测试文章/" == decoded_url

        # Check cloud destination contains the uploaded post.md and image
        expected_md = cloud_dest / "测试作者_777" / "[5566] 端到端测试文章" / "post.md"
        assert expected_md.exists()
        assert "这是段落一。" in expected_md.read_text(encoding="utf-8")

        expected_img = cloud_dest / "测试作者_777" / "[5566] 端到端测试文章" / "images" / "01.jpg"
        assert expected_img.exists()
        assert expected_img.read_bytes().startswith(b"\xff\xd8\xff")

        # Verify bot creation
        bot, dp = create_bot_and_dispatcher(settings=settings, pipeline=pipeline)
        assert bot is not None
        assert dp is not None
