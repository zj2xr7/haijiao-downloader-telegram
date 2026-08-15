"""
Scraper and layout parser for Haijiao posts and author pages.
"""
import re
from typing import List, Tuple, Optional, Dict, Any
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup, NavigableString, Tag

from src.config import Settings, settings as default_settings
from src.models import PostDetail, MediaItem, ContentSegment, AuthorSummary, AuthorPostItem
from src.core.resolver import DomainResolver
from src.utils.logger import logger
from src.utils.http_client import HttpClient, http_client as default_http_client


class HaijiaoCrawler:
    """Fetches and parses post details, layout segments, and author listings."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        resolver: Optional[DomainResolver] = None,
        http_cli: Optional[HttpClient] = None
    ):
        self.settings = settings or default_settings
        self.resolver = resolver or DomainResolver(settings=self.settings)
        self.http_client = http_cli or default_http_client

    def extract_id_from_url(self, raw_input: str) -> Tuple[str, str]:
        """
        Extracts resource kind ('post' or 'author') and resource ID from raw user input.
        Supports both full URLs and plain numeric IDs.
        """
        raw_input = raw_input.strip()
        if not raw_input:
            raise ValueError("Input string is empty.")

        # 1. Check if raw input is pure digits
        if raw_input.isdigit():
            return "post", raw_input

        # 2. Check for author patterns
        author_patterns = [
            r"/user/home\?.*uid=(\d+)",
            r"/user/(\d+)",
            r"/author/(\d+)",
            r"/user_details\?.*uid=(\d+)",
            r"uid=(\d+)"
        ]
        for pattern in author_patterns:
            match = re.search(pattern, raw_input, re.IGNORECASE)
            if match:
                return "author", match.group(1)

        # 3. Check for post patterns
        post_patterns = [
            r"/post/details\?.*pid=(\d+)",
            r"/post/(\d+)",
            r"/post/details/(\d+)",
            r"pid=(\d+)",
            r"/p/(\d+)"
        ]
        for pattern in post_patterns:
            match = re.search(pattern, raw_input, re.IGNORECASE)
            if match:
                return "post", match.group(1)

        # Fallback: check query parameters
        try:
            parsed = urlparse(raw_input)
            qs = parse_qs(parsed.query)
            if "uid" in qs and qs["uid"]:
                return "author", qs["uid"][0]
            if "pid" in qs and qs["pid"]:
                return "post", qs["pid"][0]
            if "id" in qs and qs["id"]:
                return "post", qs["id"][0]
        except Exception:
            pass

        # Final fallback: search for any sequence of 4-10 digits
        digit_match = re.search(r"\b(\d{4,10})\b", raw_input)
        if digit_match:
            return "post", digit_match.group(1)

        raise ValueError(f"Could not parse a valid post or author ID from: {raw_input}")

    def sanitize_title(self, title: str) -> str:
        """Sanitizes title string for use in folder and file names."""
        # Replace illegal filesystem characters: / \ : * ? " < > |
        clean = re.sub(r'[\\/*?:"<>|]', "", title)
        # Collapse whitespace
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean or "untitled"

    def parse_post_html(self, html_text: str, post_id: str, base_domain: str) -> PostDetail:
        """Parses HTML into a structured PostDetail object preserving layout order."""
        soup = BeautifulSoup(html_text, "html.parser")

        # 1. Title
        title_el = soup.select_one("h1, .post-title, .title, .content-title")
        title = title_el.get_text(strip=True) if title_el else f"Post {post_id}"
        title = self.sanitize_title(title)

        # 2. Author info
        author_el = soup.select_one(".author-name, .user-name, .nickname, .author, a[href*='uid=']")
        author_name = author_el.get_text(strip=True) if author_el else "Unknown_Author"
        author_name = self.sanitize_title(author_name)
        
        author_id = "0"
        if author_el and author_el.name == "a" and author_el.has_attr("href"):
            m = re.search(r"uid=(\d+)", author_el["href"])
            if m:
                author_id = m.group(1)
        elif author_el:
            parent_a = author_el.find_parent("a", href=True)
            if parent_a:
                m = re.search(r"uid=(\d+)", parent_a["href"])
                if m:
                    author_id = m.group(1)

        # 3. Publish Time
        time_el = soup.select_one(".publish-time, .time, .date, .create-time")
        publish_time = time_el.get_text(strip=True) if time_el else None

        # 4. Content container
        content_box = soup.select_one(".post-content, .article-content, .content, .detail-content") or soup.body or soup

        segments: List[ContentSegment] = []
        image_count = 0
        video_count = 0

        # Scan for elements in layout order
        # Look for p, div, img, video tags
        nodes = content_box.find_all(["p", "div", "h1", "h2", "h3", "h4", "blockquote", "img", "video"])
        visited_tags = set()

        for node in nodes:
            if id(node) in visited_tags:
                continue

            # Check if this node is an image
            if node.name == "img":
                src = node.get("src") or node.get("data-src") or node.get("data-original")
                if src and not src.startswith("data:image"):
                    image_count += 1
                    rel_path = f"images/{image_count:02d}.jpg"
                    if not src.startswith("http"):
                        src = f"{base_domain.rstrip('/')}/{src.lstrip('/')}"
                    
                    media_item = MediaItem(
                        media_type="image",
                        remote_url=src,
                        relative_path=rel_path,
                        encryption_type="header_xor" if (".enc" in src or "encrypt" in src) else "none"
                    )
                    segments.append(ContentSegment(segment_type="image", media_item=media_item))
                    visited_tags.add(id(node))
                continue

            # Check if this node is a video
            if node.name == "video" or node.select_one("video") or ("dplayer" in node.get("class", [])):
                video_el = node if node.name == "video" else node.select_one("video")
                src = None
                if video_el:
                    src = video_el.get("src") or video_el.get("data-src")
                    if not src:
                        source_tag = video_el.select_one("source")
                        if source_tag:
                            src = source_tag.get("src")
                if not src:
                    # check dataset or attributes
                    src = node.get("data-url") or node.get("data-video-url")

                if src:
                    video_count += 1
                    rel_path = f"videos/{video_count:02d}.mp4"
                    if not src.startswith("http"):
                        src = f"{base_domain.rstrip('/')}/{src.lstrip('/')}"
                    
                    enc_type = "aes-128" if (".m3u8" in src or "hls" in src) else "none"
                    media_item = MediaItem(
                        media_type="video",
                        remote_url=src,
                        relative_path=rel_path,
                        encryption_type=enc_type
                    )
                    segments.append(ContentSegment(segment_type="video", media_item=media_item))
                    visited_tags.add(id(node))
                continue

            # Text blocks (paragraphs, headings, quotes)
            # Skip if this node contains nested p / div to avoid duplicates
            if node.find(["p", "div", "blockquote"]):
                continue

            text = node.get_text(strip=True)
            if text:
                seg_type = "text"
                if node.name in ("h1", "h2", "h3", "h4"):
                    seg_type = "heading"
                elif node.name == "blockquote":
                    seg_type = "quote"

                segments.append(ContentSegment(segment_type=seg_type, text_content=text))
                visited_tags.add(id(node))

        return PostDetail(
            post_id=post_id,
            title=title,
            author_id=author_id,
            author_name=author_name,
            publish_time=publish_time,
            source_url=f"{base_domain}/post/details?pid={post_id}",
            content_segments=segments,
            total_images=image_count,
            total_videos=video_count
        )

    async def fetch_post_detail(self, post_id: str) -> PostDetail:
        """Fetches and parses the target post from the active mirror domain."""
        domain = await self.resolver.get_active_domain()
        target_url = f"{domain}/post/details?pid={post_id}"
        logger.info(f"Fetching post {post_id} from {target_url}...")

        try:
            resp = await self.http_client.get(target_url)
            if resp.status_code == 200:
                return self.parse_post_html(resp.text, post_id=post_id, base_domain=domain)
            elif resp.status_code in (403, 502, 503):
                # Attempt with forced refreshed domain
                logger.warning(f"Got status {resp.status_code}, refreshing mirror domain...")
                domain = await self.resolver.get_active_domain(force_refresh=True)
                target_url = f"{domain}/post/details?pid={post_id}"
                resp = await self.http_client.get(target_url)
                if resp.status_code == 200:
                    return self.parse_post_html(resp.text, post_id=post_id, base_domain=domain)
            raise RuntimeError(f"Failed to fetch post {post_id}: HTTP {resp.status_code}")
        except Exception as exc:
            logger.error(f"Error fetching post {post_id}: {exc}")
            raise

    async def fetch_author_summary(self, author_id: str) -> AuthorSummary:
        """Fetches author profile and calculates available post pages."""
        domain = await self.resolver.get_active_domain()
        url = f"{domain}/user/home?uid={author_id}"
        logger.info(f"Fetching author {author_id} from {url}...")

        try:
            resp = await self.http_client.get(url)
            if resp.status_code != 200:
                domain = await self.resolver.get_active_domain(force_refresh=True)
                url = f"{domain}/user/home?uid={author_id}"
                resp = await self.http_client.get(url)

            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                name_el = soup.select_one(".nickname, .username, .author-name, h1, h2")
                author_name = name_el.get_text(strip=True) if name_el else f"Author_{author_id}"
                author_name = self.sanitize_title(author_name)

                # Estimate total posts / pages
                posts_count_el = soup.select_one(".post-count, .stats-posts")
                total_posts = 10
                if posts_count_el:
                    m = re.search(r"(\d+)", posts_count_el.get_text())
                    if m:
                        total_posts = int(m.group(1))

                total_pages = max(1, (total_posts + 9) // 10)
                return AuthorSummary(
                    author_id=author_id,
                    author_name=author_name,
                    total_posts=total_posts,
                    total_pages=total_pages
                )
            raise RuntimeError(f"Failed to fetch author {author_id}: HTTP {resp.status_code}")
        except Exception as exc:
            logger.error(f"Error fetching author summary {author_id}: {exc}")
            return AuthorSummary(author_id=author_id, author_name=f"Author_{author_id}", total_posts=10, total_pages=1)

    async def fetch_author_posts(self, author_id: str, page: int) -> List[AuthorPostItem]:
        """Fetches post items on a given author page."""
        domain = await self.resolver.get_active_domain()
        url = f"{domain}/user/home?uid={author_id}&page={page}"
        logger.info(f"Fetching author {author_id} page {page} from {url}...")

        items: List[AuthorPostItem] = []
        try:
            resp = await self.http_client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                post_links = soup.select("a[href*='pid='], a[href*='/post/']")
                seen_pids = set()

                for link in post_links:
                    href = link.get("href", "")
                    m = re.search(r"pid=(\d+)|/post/(\d+)", href)
                    if m:
                        pid = m.group(1) or m.group(2)
                        if pid not in seen_pids:
                            seen_pids.add(pid)
                            title = link.get_text(strip=True) or f"Post {pid}"
                            items.append(AuthorPostItem(post_id=pid, title=self.sanitize_title(title)))
        except Exception as exc:
            logger.error(f"Error fetching author page {page}: {exc}")

        return items
