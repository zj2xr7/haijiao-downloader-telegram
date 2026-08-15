"""
Tests for HaijiaoCrawler.
"""
import pytest
from src.core.crawler import HaijiaoCrawler
from src.config import Settings


def test_extract_id_from_url():
    crawler = HaijiaoCrawler(settings=Settings(BOT_TOKEN="fake", ALLOWED_USER_IDS="123"))
    
    # 1. Post URLs
    kind, target_id = crawler.extract_id_from_url("https://hjabc.com/archives/191635/")
    assert kind == "post"
    assert target_id == "191635"

    kind, target_id = crawler.extract_id_from_url("https://hjabc.com/post/details?pid=987654")
    assert kind == "post"
    assert target_id == "987654"
    
    kind, target_id = crawler.extract_id_from_url("https://hjabc.com/post/12345")
    assert kind == "post"
    assert target_id == "12345"

    # 2. Raw Digits
    kind, target_id = crawler.extract_id_from_url("887766")
    assert kind == "post"
    assert target_id == "887766"

    # 3. Author URLs
    kind, target_id = crawler.extract_id_from_url("https://hjabc.com/author/115/new/")
    assert kind == "author"
    assert target_id == "115"

    kind, target_id = crawler.extract_id_from_url("https://hjabc.com/user/home?uid=54321")
    assert kind == "author"
    assert target_id == "54321"

    kind, target_id = crawler.extract_id_from_url("https://hjabc.com/author/999")
    assert kind == "author"
    assert target_id == "999"


def test_parse_post_html_layout():
    crawler = HaijiaoCrawler()
    sample_html = """
    <html>
        <body>
            <h1 class="post-title">精彩的一天 / 排版测试</h1>
            <div class="author-info">
                <a href="/author/888/new/" class="author-name">海角小创作者3681568</a>
                <span class="publish-time">2026-08-15 21:00:00</span>
            </div>
            <div class="text text-content">
                <p>今天天气非常好，记录一下日常。</p>
                <img z-image-loader-url="https://img.example.com/photo1.enc" />
                <p>接着是下午的视频记录：</p>
                <div class="videoplayer dplayer" data-config='{"video":{"url":"https://video.example.com/stream.m3u8"}}'></div>
                <p>感谢大家的观看！</p>
            </div>
        </body>
    </html>
    """
    post = crawler.parse_post_html(sample_html, post_id="9988", base_domain="https://example.com")
    
    assert post.post_id == "9988"
    assert "精彩的一天" in post.title
    assert post.author_name == "海角小创作者"
    assert post.author_id == "888"
    assert post.total_images == 1
    assert post.total_videos == 1
    assert len(post.content_segments) == 5
    
    # Check layout order
    assert post.content_segments[0].segment_type == "text"
    assert post.content_segments[1].segment_type == "image"
    assert post.content_segments[1].media_item.relative_path == "images/01.jpg"
    assert post.content_segments[1].media_item.remote_url == "https://img.example.com/photo1.enc"
    assert post.content_segments[2].segment_type == "text"
    assert post.content_segments[3].segment_type == "video"
    assert post.content_segments[3].media_item.relative_path == "videos/01.mp4"
    assert post.content_segments[3].media_item.remote_url == "https://video.example.com/stream.m3u8"
    assert post.content_segments[4].segment_type == "text"
