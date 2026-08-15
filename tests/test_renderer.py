"""
Tests for MarkdownRenderer.
"""
import pytest
from pathlib import Path
from src.core.renderer import MarkdownRenderer
from src.models import PostDetail, MediaItem, ContentSegment


def test_markdown_rendering_complete(tmp_path):
    renderer = MarkdownRenderer()
    post = PostDetail(
        post_id="888",
        title="Test Title",
        author_id="u12",
        author_name="Bob",
        publish_time="2026-08-15 12:00:00",
        source_url="https://example.com/post/888",
        content_segments=[
            ContentSegment(segment_type="text", text_content="First paragraph."),
            ContentSegment(
                segment_type="image",
                media_item=MediaItem(
                    media_type="image",
                    remote_url="http://a.com/1.jpg",
                    relative_path="images/01.jpg",
                    download_success=True
                )
            ),
            ContentSegment(segment_type="text", text_content="Second paragraph."),
            ContentSegment(
                segment_type="video",
                media_item=MediaItem(
                    media_type="video",
                    remote_url="http://a.com/1.m3u8",
                    relative_path="videos/01.mp4",
                    download_success=True
                )
            )
        ]
    )

    md_text = renderer.render_post_markdown(post)
    assert "# Test Title" in md_text
    assert "First paragraph." in md_text
    assert "![图片 1](./images/01.jpg)" in md_text
    assert "Second paragraph." in md_text
    assert '<video controls src="./videos/01.mp4" width="100%"></video>' in md_text

    # Test file saving & folder structure
    post_dir = renderer.prepare_post_directory(post, tmp_path)
    assert (post_dir / "images").exists()
    assert (post_dir / "videos").exists()
    assert post_dir.name == "[888] Test Title"
    assert post_dir.parent.name == "Bob_u12"

    md_file = renderer.save_markdown_file(post, post_dir)
    assert md_file.exists()
    assert md_file.read_text(encoding="utf-8") == md_text
