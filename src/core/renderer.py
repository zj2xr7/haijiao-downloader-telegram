"""
Markdown layout renderer and directory packager for posts.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models import PostDetail, ContentSegment
from src.utils.logger import logger


class MarkdownRenderer:
    """Renders structured PostDetail content into readable Markdown with relative media links."""

    def render_post_markdown(self, post: PostDetail) -> str:
        """Serializes PostDetail into Markdown format with YAML frontmatter."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. Frontmatter
        lines = [
            "---",
            f'title: "{post.title}"',
            f'author: "{post.author_name}"',
            f'author_id: "{post.author_id}"',
            f'post_id: "{post.post_id}"',
            f'publish_time: "{post.publish_time or "未知"}"',
            f'source_url: "{post.source_url}"',
            f'downloaded_at: "{now_str}"',
            "---",
            "",
            f"# {post.title}",
            "",
            f"> 👤 **原作者**: **{post.author_name}**  ",
            f"> 📅 **发布时间**: {post.publish_time or '未知'}  ",
            f"> 🆔 **帖子编号**: {post.post_id}  ",
            f"> 🔗 **原始来源**: [{post.source_url}]({post.source_url})",
            "",
            "---",
            ""
        ]

        img_idx = 0
        video_idx = 0

        # 2. Body Segments
        for seg in post.content_segments:
            if seg.segment_type == "text" and seg.text_content:
                lines.append(seg.text_content)
                lines.append("")
            elif seg.segment_type == "heading" and seg.text_content:
                lines.append(f"## {seg.text_content}")
                lines.append("")
            elif seg.segment_type == "quote" and seg.text_content:
                lines.append(f"> {seg.text_content}")
                lines.append("")
            elif seg.segment_type == "image" and seg.media_item:
                img_idx += 1
                media = seg.media_item
                rel_path = media.relative_path.replace("\\", "/")
                if media.download_success or not hasattr(media, "download_success"):
                    lines.append(f"![图片 {img_idx}](./{rel_path})")
                else:
                    lines.append(f"<!-- ⚠️ 图片下载失败: {media.remote_url} -->")
                lines.append("")
            elif seg.segment_type == "video" and seg.media_item:
                video_idx += 1
                media = seg.media_item
                rel_path = media.relative_path.replace("\\", "/")
                if media.download_success or not hasattr(media, "download_success"):
                    lines.append(f'<video controls src="./{rel_path}" width="100%"></video>')
                else:
                    lines.append(f"<!-- ⚠️ 视频下载失败: {media.remote_url} -->")
                lines.append("")

        return "\n".join(lines).strip() + "\n"

    def get_author_folder_name(self, post: PostDetail) -> str:
        """Generates author directory name."""
        return f"{post.author_name}_{post.author_id}"

    def get_post_folder_name(self, post: PostDetail) -> str:
        """Generates post directory name."""
        return f"[{post.post_id}] {post.title}"

    def prepare_post_directory(self, post: PostDetail, base_dir: Path) -> Path:
        """
        Creates directory structure for the post and initializes images/videos folders.
        Returns the specific post directory Path.
        """
        author_folder = self.get_author_folder_name(post)
        post_folder = self.get_post_folder_name(post)

        post_dir = base_dir / author_folder / post_folder
        (post_dir / "images").mkdir(parents=True, exist_ok=True)
        (post_dir / "videos").mkdir(parents=True, exist_ok=True)

        return post_dir

    def save_markdown_file(self, post: PostDetail, post_dir: Path) -> Path:
        """Renders and writes post.md inside post_dir."""
        content = self.render_post_markdown(post)
        md_path = post_dir / "post.md"
        md_path.write_text(content, encoding="utf-8")
        logger.info(f"Generated Markdown layout at {md_path}")
        return md_path
