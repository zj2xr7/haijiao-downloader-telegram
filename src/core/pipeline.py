"""
Full duplex download-upload pipeline manager and job coordinator.
"""
import time
import asyncio
from pathlib import Path
from typing import Optional, Callable, List, AsyncGenerator

from src.models import PostDetail, TaskResult, TaskStage
from src.config import Settings, settings as default_settings
from src.core.crawler import HaijiaoCrawler
from src.core.decryptor import MediaDecryptor
from src.core.renderer import MarkdownRenderer
from src.core.disk_guard import DiskGuard
from src.core.uploader import RcloneUploader
from src.utils.logger import logger


class PipelineManager:
    """Coordinates post fetching, media decryption, layout generation, uploading and cleanup."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        crawler: Optional[HaijiaoCrawler] = None,
        decryptor: Optional[MediaDecryptor] = None,
        renderer: Optional[MarkdownRenderer] = None,
        disk_guard: Optional[DiskGuard] = None,
        uploader: Optional[RcloneUploader] = None
    ):
        self.settings = settings or default_settings
        self.crawler = crawler or HaijiaoCrawler(settings=self.settings)
        self.decryptor = decryptor or MediaDecryptor(settings=self.settings)
        self.renderer = renderer or MarkdownRenderer()
        self.disk_guard = disk_guard or DiskGuard(settings=self.settings)
        self.uploader = uploader or RcloneUploader(settings=self.settings, disk_guard=self.disk_guard)

    async def _download_media_assets(self, post: PostDetail, post_dir: Path, progress_callback: Optional[Callable] = None) -> None:
        """Downloads and decrypts all media items referenced in the post."""
        img_success = 0
        video_success = 0

        for seg in post.content_segments:
            if seg.segment_type == "image" and seg.media_item:
                media = seg.media_item
                out_file = post_dir / media.relative_path
                ok = await self.decryptor.download_and_decrypt_image(media, out_file)
                if ok:
                    img_success += 1
            elif seg.segment_type == "video" and seg.media_item:
                media = seg.media_item
                out_file = post_dir / media.relative_path
                ok = await self.decryptor.download_and_decrypt_video_m3u8(media, out_file)
                if ok:
                    video_success += 1

            if progress_callback:
                try:
                    await progress_callback(
                        post.post_id,
                        f"📥 正在抓取媒体资源 (已完成图片: {img_success}/{post.total_images}, 视频: {video_success}/{post.total_videos})"
                    )
                except Exception:
                    pass

    async def process_single_post(
        self,
        post_id: str,
        progress_callback: Optional[Callable] = None
    ) -> TaskResult:
        """
        Executes the full pipeline for a single post:
        1. Fetch metadata & layout
        2. Wait for DiskGuard clearance
        3. Download & decrypt media
        4. Render post.md
        5. Release download slot immediately
        6. Asynchronously upload to OneDrive & cleanup local temp folder
        7. Generate OpenList link
        """
        start_time = time.monotonic()
        logger.info(f"Pipeline: Starting processing for post {post_id}")

        if progress_callback:
            await progress_callback(post_id, "🔍 正在解析文章元数据与排版结构...")

        # 1. Fetch Post Detail
        try:
            post = await self.crawler.fetch_post_detail(post_id)
        except Exception as exc:
            logger.error(f"Failed to parse post {post_id}: {exc}")
            return TaskResult(
                post_id=post_id,
                title="Unknown",
                author_name="Unknown",
                stage=TaskStage.FAILED,
                error_message=f"解析帖子结构失败: {exc}",
                elapsed_seconds=round(time.monotonic() - start_time, 2)
            )

        # 2. Wait for DiskGuard clearance
        if progress_callback:
            free_gb = self.disk_guard.get_free_space_gb()
            await progress_callback(post_id, f"🛡️ 磁盘检查通过 ({free_gb} GB 可用)，开始下载...")

        await self.disk_guard.acquire_download_slot()
        post_dir = self.renderer.prepare_post_directory(post, self.settings.temp_download_path)

        # 3. Download & Decrypt Media Assets
        try:
            await self._download_media_assets(post, post_dir, progress_callback)
            # 4. Render Markdown
            if progress_callback:
                await progress_callback(post_id, "📝 正在生成 Markdown 排版...")
            self.renderer.save_markdown_file(post, post_dir)
        except Exception as exc:
            logger.error(f"Error during download/rendering for post {post_id}: {exc}")
            self.disk_guard.release_download_slot()
            return TaskResult(
                post_id=post_id,
                title=post.title,
                author_name=post.author_name,
                stage=TaskStage.FAILED,
                error_message=f"下载或排版过程异常: {exc}",
                elapsed_seconds=round(time.monotonic() - start_time, 2)
            )
        finally:
            # Release download slot so the next post can start downloading
            self.disk_guard.release_download_slot()

        # 5. Upload via Rclone in background
        author_folder = self.renderer.get_author_folder_name(post)
        post_folder = self.renderer.get_post_folder_name(post)
        remote_subpath = f"{author_folder}/{post_folder}"

        if progress_callback:
            await progress_callback(post_id, "☁️ 本地排版完成，正在上传到 OneDrive...")

        upload_ok, err_msg = await self.uploader.upload_and_cleanup(post_dir, remote_subpath)

        elapsed = round(time.monotonic() - start_time, 2)
        if upload_ok:
            openlist_link = self.uploader.get_openlist_url(author_folder, post_folder)
            logger.info(f"Pipeline: Successfully processed post {post_id} in {elapsed}s -> {openlist_link}")
            return TaskResult(
                post_id=post_id,
                title=post.title,
                author_name=post.author_name,
                stage=TaskStage.COMPLETED,
                openlist_url=openlist_link,
                elapsed_seconds=elapsed,
                downloaded_images=post.total_images,
                downloaded_videos=post.total_videos
            )
        else:
            logger.error(f"Pipeline: Upload failed for post {post_id}: {err_msg}")
            return TaskResult(
                post_id=post_id,
                title=post.title,
                author_name=post.author_name,
                stage=TaskStage.FAILED,
                error_message=f"上传至云存储失败: {err_msg}",
                elapsed_seconds=elapsed
            )

    async def process_author_pages(
        self,
        author_id: str,
        pages: List[int],
        post_progress_callback: Optional[Callable] = None
    ) -> AsyncGenerator[TaskResult, None]:
        """Iterates over requested author pages and processes each post in sequence."""
        for page in pages:
            logger.info(f"Pipeline: Fetching post list for author {author_id} on page {page}...")
            post_items = await self.crawler.fetch_author_posts(author_id, page)
            for item in post_items:
                res = await self.process_single_post(item.post_id, progress_callback=post_progress_callback)
                yield res
