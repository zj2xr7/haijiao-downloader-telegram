"""
Full duplex download-upload pipeline manager and job coordinator.
"""
import time
import inspect
import asyncio
from pathlib import Path
from typing import Optional, Callable, List, AsyncGenerator, Dict, Any

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

    async def _emit_progress(
        self,
        callback: Optional[Callable],
        post_id: str,
        stage_desc: str,
        title: str = "",
        author: str = "",
        stage: TaskStage = TaskStage.DOWNLOADING,
        percent: int = 0,
        media_detail: str = ""
    ) -> None:
        """Safely invokes progress callback adapting to any parameter signature."""
        if not callback:
            return
        try:
            sig = inspect.signature(callback)
            params = list(sig.parameters.values())

            # Check if callback accepts kwargs or exact 2 positional args
            if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params):
                res = callback(
                    post_id=post_id,
                    stage_desc=stage_desc,
                    title=title,
                    author=author,
                    stage=stage,
                    percent=percent,
                    media_detail=media_detail
                )
            elif len(params) == 2:
                # Classic (post_id, text) callback signature
                res = callback(post_id, stage_desc)
            else:
                # Try calling with keyword arguments
                res = callback(
                    post_id=post_id,
                    stage_desc=stage_desc,
                    title=title,
                    author=author,
                    stage=stage,
                    percent=percent,
                    media_detail=media_detail
                )

            if inspect.isawaitable(res):
                await res
        except Exception as exc:
            logger.debug(f"Progress callback invocation skipped: {exc}")

    async def _download_media_assets(
        self,
        post: PostDetail,
        post_dir: Path,
        progress_callback: Optional[Callable] = None
    ) -> None:
        """Downloads and decrypts all media items referenced in the post."""
        img_success = 0
        video_success = 0

        for idx, seg in enumerate(post.content_segments):
            if seg.segment_type == "image" and seg.media_item:
                media = seg.media_item
                out_file = post_dir / media.relative_path
                await self._emit_progress(
                    progress_callback,
                    post_id=post.post_id,
                    stage_desc=f"🖼️ 正在下载并解密图片 [{img_success + 1}/{post.total_images}]...",
                    title=post.title,
                    author=post.author_name,
                    stage=TaskStage.DOWNLOADING,
                    percent=int((img_success / max(1, post.total_images)) * 50)
                )
                ok = await self.decryptor.download_and_decrypt_image(media, out_file)
                if ok:
                    img_success += 1

            elif seg.segment_type == "video" and seg.media_item:
                media = seg.media_item
                out_file = post_dir / media.relative_path

                async def on_video_progress(completed: int, total: int, status_text: str):
                    pct = int((completed / max(1, total)) * 100)
                    await self._emit_progress(
                        progress_callback,
                        post_id=post.post_id,
                        stage_desc=f"🎬 <b>[视频下载]</b> {status_text}",
                        title=post.title,
                        author=post.author_name,
                        stage=TaskStage.DOWNLOADING,
                        percent=pct,
                        media_detail=f"TS 分片: {completed}/{total}"
                    )

                ok = await self.decryptor.download_and_decrypt_video_m3u8(
                    media, out_file, progress_callback=on_video_progress
                )
                if ok:
                    video_success += 1

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

        await self._emit_progress(
            progress_callback,
            post_id=post_id,
            stage_desc="🔍 [1/4] 正在解析文章元数据与排版结构...",
            title=f"Post {post_id}",
            author="加载中...",
            stage=TaskStage.RESOLVING,
            percent=10
        )

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
        free_gb = self.disk_guard.get_free_space_gb()
        await self._emit_progress(
            progress_callback,
            post_id=post_id,
            stage_desc=f"🛡️ [2/4] 磁盘检查通过 ({free_gb} GB 可用)，准备下载媒体...",
            title=post.title,
            author=post.author_name,
            stage=TaskStage.DOWNLOADING,
            percent=25
        )

        await self.disk_guard.acquire_download_slot()
        post_dir = self.renderer.prepare_post_directory(post, self.settings.temp_download_path)

        # 3. Download & Decrypt Media Assets
        try:
            await self._download_media_assets(post, post_dir, progress_callback)
            
            # 4. Render Markdown
            await self._emit_progress(
                progress_callback,
                post_id=post_id,
                stage_desc="📝 [3/4] 媒体就绪，正在生成 Markdown 图文排版与元数据...",
                title=post.title,
                author=post.author_name,
                stage=TaskStage.RENDERING,
                percent=85
            )
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
            # Release download slot so next post can begin downloading immediately
            self.disk_guard.release_download_slot()

        # 5. Upload via Rclone in background
        author_folder = self.renderer.get_author_folder_name(post)
        post_folder = self.renderer.get_post_folder_name(post)
        remote_subpath = f"{author_folder}/{post_folder}"

        await self._emit_progress(
            progress_callback,
            post_id=post_id,
            stage_desc="☁️ [4/4] 本地排版完成，正在通过 Rclone 上传至 OneDrive...",
            title=post.title,
            author=post.author_name,
            stage=TaskStage.UPLOADING,
            percent=95
        )

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
