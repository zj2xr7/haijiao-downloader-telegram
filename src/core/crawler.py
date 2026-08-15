"""
Scraper and layout parser for Haijiao posts and author pages.
"""
import re
import json
from typing import List, Tuple, Optional, Dict, Any, Set
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup, NavigableString, Tag

from src.config import Settings, settings as default_settings
from src.models import PostDetail, MediaItem, ContentSegment, AuthorSummary, AuthorPostItem
from src.core.resolver import DomainResolver
from src.utils.logger import logger
from src.utils.http_client import HttpClient, http_client as default_http_client


IGNORED_IMG_KEYWORDS = {
    "rank1", "rank2", "rank3", "rank", "logo", "avatar", "icon", "favicon",
    "badge", "ad", "default", "loading", "banner"
}


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
            r"/author/(\d+)",
            r"/user/home\?.*uid=(\d+)",
            r"/user/(\d+)",
            r"/user_details\?.*uid=(\d+)",
            r"uid=(\d+)"
        ]
        for pattern in author_patterns:
            match = re.search(pattern, raw_input, re.IGNORECASE)
            if match:
                return "author", match.group(1)

        # 3. Check for post patterns
        post_patterns = [
            r"/archives/(\d+)",
            r"/post/details\?.*pid=(\d+)",
            r"/post/details/(\d+)",
            r"/post/(\d+)",
            r"/community/(\d+)",
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
        clean = re.sub(r'[\\/*?:"<>|]', "", title)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean or "untitled"

    def parse_post_html(self, html_text: str, post_id: str, base_domain: str) -> PostDetail:
        """Parses HTML into a structured PostDetail object preserving layout order."""
        soup = BeautifulSoup(html_text, "html.parser")

        # 1. Title
        title = ""
        title_el = soup.select_one("h1, .post-title, .title, .content-title, .article-title")
        if title_el:
            title = title_el.get_text(strip=True)
        elif soup.title:
            title = soup.title.string.split("|")[0].split("-")[0].strip()
        title = self.sanitize_title(title or f"Post {post_id}")

        # 2. Author info
        author_name = "未知创作者"
        author_id = "0"
        author_link = soup.find("a", href=lambda h: h and ("/author/" in h or "/user/" in h or "uid=" in h))
        if author_link:
            raw_author_text = author_link.get_text(strip=True)
            # Remove trailing numbers like "奶子即正义3681568" -> "奶子即正义"
            cleaned_name = re.sub(r"\d{4,}.*$", "", raw_author_text).strip()
            author_name = cleaned_name or raw_author_text or f"Author_{post_id}"
            href = author_link.get("href", "")
            m = re.search(r"/(?:author|user)/(\d+)|uid=(\d+)", href)
            if m:
                author_id = m.group(1) or m.group(2)
        else:
            author_el = soup.select_one(".author-name, .user-name, .nickname, .author")
            if author_el:
                author_name = author_el.get_text(strip=True)

        author_name = self.sanitize_title(author_name)

        # 3. Publish Time
        time_el = soup.select_one(".publish-time, .time, .date, .create-time, .detail-info-desc")
        publish_time = time_el.get_text(strip=True) if time_el else None

        # 4. Content container
        content_box = (
            soup.find("div", class_=lambda c: c and "text-content" in c)
            or soup.find("article")
            or soup.find("div", class_=lambda c: c and ("xqbj-main" in c or "detail" in c or "post-content" in c))
            or soup.body
            or soup
        )

        segments: List[ContentSegment] = []
        image_count = 0
        video_count = 0
        seen_media_urls: Set[str] = set()

        # Helper to register a video item
        def add_video_segment(v_url: str):
            nonlocal video_count
            if not v_url or v_url in seen_media_urls:
                return
            seen_media_urls.add(v_url)
            video_count += 1
            rel_path = f"videos/{video_count:02d}.mp4"
            if not v_url.startswith("http"):
                v_url = f"{base_domain.rstrip('/')}/{v_url.lstrip('/')}"
            
            enc_type = "aes-128" if (".m3u8" in v_url or "hls" in v_url) else "none"
            media_item = MediaItem(
                media_type="video",
                remote_url=v_url,
                relative_path=rel_path,
                encryption_type=enc_type
            )
            segments.append(ContentSegment(segment_type="video", media_item=media_item))

        # Helper to register an image item
        def add_image_segment(img_url: str):
            nonlocal image_count
            if not img_url or img_url in seen_media_urls:
                return
            # Filter UI icons / ads
            if any(ign in img_url.lower() for ign in IGNORED_IMG_KEYWORDS):
                return
            seen_media_urls.add(img_url)
            image_count += 1
            rel_path = f"images/{image_count:02d}.jpg"
            if not img_url.startswith("http"):
                img_url = f"{base_domain.rstrip('/')}/{img_url.lstrip('/')}"

            enc_type = "header_xor" if (".enc" in img_url or "encrypt" in img_url) else "none"
            media_item = MediaItem(
                media_type="image",
                remote_url=img_url,
                relative_path=rel_path,
                encryption_type=enc_type
            )
            segments.append(ContentSegment(segment_type="image", media_item=media_item))

        # Scan for tags in DOM layout order
        nodes = content_box.find_all([
            "p", "div", "h1", "h2", "h3", "h4", "blockquote", "img", "video"
        ])
        visited_nodes = set()

        for node in nodes:
            if id(node) in visited_nodes:
                continue

            # A. Check for DPlayer video container (div.dplayer or div.videoplayer with data-config)
            classes = node.get("class", [])
            data_config_raw = node.get("data-config")
            if any(c in classes for c in ["dplayer", "videoplayer"]) or data_config_raw:
                if data_config_raw:
                    try:
                        cfg_obj = json.loads(data_config_raw)
                        v_url = (
                            cfg_obj.get("video", {}).get("url")
                            or cfg_obj.get("video_h265", {}).get("url")
                        )
                        if v_url:
                            add_video_segment(v_url)
                            visited_nodes.add(id(node))
                            continue
                    except Exception as exc:
                        logger.debug(f"Failed parsing data-config JSON on dplayer node: {exc}")

            # B. Check for standard video / source tag
            if node.name == "video":
                src = node.get("src") or node.get("data-src")
                if not src:
                    source_tag = node.select_one("source")
                    if source_tag:
                        src = source_tag.get("src")
                if src:
                    add_video_segment(src)
                    visited_nodes.add(id(node))
                    continue

            # C. Check for image tag
            if node.name == "img":
                src = (
                    node.get("z-image-loader-url")
                    or node.get("data-src")
                    or node.get("data-original")
                    or node.get("src")
                )
                if src and not src.startswith("data:image"):
                    add_image_segment(src)
                    visited_nodes.add(id(node))
                continue

            # D. Text blocks (paragraphs, headings, blockquotes)
            # Skip if this container has nested block children to prevent duplicate text
            if node.find(["p", "div", "blockquote", "h1", "h2", "h3", "h4"]):
                continue

            text = node.get_text(strip=True)
            if text and len(text) > 1:
                seg_type = "text"
                if node.name in ("h1", "h2", "h3", "h4"):
                    seg_type = "heading"
                elif node.name == "blockquote":
                    seg_type = "quote"

                segments.append(ContentSegment(segment_type=seg_type, text_content=text))
                visited_nodes.add(id(node))

        # Fallback: if no video segment found in layout nodes, scan whole HTML for script-embedded m3u8
        if video_count == 0:
            for s in soup.find_all("script"):
                text = s.string or s.text or ""
                m3u8_matches = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', text)
                for m_url in m3u8_matches:
                    add_video_segment(m_url)

        return PostDetail(
            post_id=post_id,
            title=title,
            author_id=author_id,
            author_name=author_name,
            publish_time=publish_time,
            source_url=f"{base_domain}/archives/{post_id}/",
            content_segments=segments,
            total_images=image_count,
            total_videos=video_count
        )

    async def fetch_post_detail(self, post_id: str) -> PostDetail:
        """
        Fetches and parses the target post from the active mirror domain.
        Probes multiple route candidates (/archives/{id}/, /post/details?pid={id}, etc.).
        """
        domain = await self.resolver.get_active_domain()
        candidate_paths = [
            f"/archives/{post_id}/",
            f"/archives/{post_id}",
            f"/post/details?pid={post_id}",
            f"/post/{post_id}",
            f"/community/{post_id}/"
        ]

        logger.info(f"Fetching post {post_id} from mirror {domain}...")

        # 1. Probe candidate routes with current active domain
        for path in candidate_paths:
            target_url = f"{domain}{path}"
            try:
                resp = await self.http_client.get(target_url)
                if resp.status_code == 200:
                    logger.info(f"Successfully retrieved post {post_id} from {target_url}")
                    return self.parse_post_html(resp.text, post_id=post_id, base_domain=domain)
            except Exception as exc:
                logger.debug(f"Route {target_url} failed: {exc}")

        # 2. If all routes failed, force refresh mirror domain and retry
        logger.warning(f"All routes for post {post_id} failed on {domain}, refreshing mirror domain...")
        domain = await self.resolver.get_active_domain(force_refresh=True)

        for path in candidate_paths:
            target_url = f"{domain}{path}"
            try:
                resp = await self.http_client.get(target_url)
                if resp.status_code == 200:
                    logger.info(f"Successfully retrieved post {post_id} from refreshed mirror {target_url}")
                    return self.parse_post_html(resp.text, post_id=post_id, base_domain=domain)
            except Exception as exc:
                logger.debug(f"Refreshed route {target_url} failed: {exc}")

        raise RuntimeError(f"Failed to fetch post {post_id}: HTTP 404 (tested all candidate paths on active mirror)")

    async def fetch_author_summary(self, author_id: str) -> AuthorSummary:
        """Fetches author profile and calculates available post pages."""
        domain = await self.resolver.get_active_domain()
        candidate_urls = [
            f"{domain}/author/{author_id}/new/",
            f"{domain}/author/{author_id}/",
            f"{domain}/user/{author_id}/",
            f"{domain}/user/home?uid={author_id}"
        ]

        for url in candidate_urls:
            try:
                resp = await self.http_client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    name_el = soup.select_one(".nickname, .username, .author-name, h1, h2, title")
                    raw_name = name_el.get_text(strip=True) if name_el else f"Author_{author_id}"
                    raw_name = raw_name.split("|")[0].split("-")[0].strip()
                    cleaned_name = re.sub(r"\d{4,}.*$", "", raw_name).strip()
                    author_name = self.sanitize_title(cleaned_name or raw_name or f"Author_{author_id}")

                    # Estimate total pages from pagination links
                    page_nums = [1]
                    for a in soup.find_all("a", href=True):
                        h = a["href"]
                        m = re.search(r"/page/(\d+)", h)
                        if m:
                            page_nums.append(int(m.group(1)))
                    total_pages = max(page_nums)
                    total_posts = total_pages * 10

                    return AuthorSummary(
                        author_id=author_id,
                        author_name=author_name,
                        total_posts=total_posts,
                        total_pages=total_pages
                    )
            except Exception as exc:
                logger.debug(f"Author route {url} probe failed: {exc}")

        return AuthorSummary(author_id=author_id, author_name=f"Author_{author_id}", total_posts=10, total_pages=1)

    async def fetch_author_posts(self, author_id: str, page: int) -> List[AuthorPostItem]:
        """Fetches post items on a given author page."""
        domain = await self.resolver.get_active_domain()
        candidate_urls = (
            [
                f"{domain}/author/{author_id}/new/",
                f"{domain}/author/{author_id}/",
                f"{domain}/user/{author_id}/"
            ]
            if page == 1
            else [
                f"{domain}/author/{author_id}/new/page/{page}/",
                f"{domain}/author/{author_id}/page/{page}/",
                f"{domain}/user/{author_id}/page/{page}/",
                f"{domain}/author/{author_id}/?page={page}"
            ]
        )

        items: List[AuthorPostItem] = []
        seen_pids = set()

        for url in candidate_urls:
            try:
                resp = await self.http_client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for link in soup.find_all("a", href=True):
                        href = link["href"]
                        m = re.search(r"/archives/(\d+)|pid=(\d+)|/post/(\d+)", href)
                        if m:
                            pid = m.group(1) or m.group(2) or m.group(3)
                            if pid and pid not in seen_pids:
                                seen_pids.add(pid)
                                title = link.get_text(strip=True) or link.get("title", "") or f"Post {pid}"
                                items.append(AuthorPostItem(post_id=pid, title=self.sanitize_title(title)))
                    if items:
                        break
            except Exception as exc:
                logger.debug(f"Author page url {url} failed: {exc}")

        return items
