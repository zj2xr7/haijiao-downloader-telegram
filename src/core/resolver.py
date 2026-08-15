"""
Dynamic domain discovery and probing from the publishing page (https://hjw2026.com).
"""
import re
import time
import asyncio
from typing import List, Optional, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import httpx

from src.config import Settings, settings as default_settings
from src.utils.logger import logger
from src.utils.http_client import HttpClient, http_client as default_http_client


class DomainResolver:
    """Discovers and maintains the currently active, reachable mirror domain for Haijiao."""

    def __init__(self, settings: Optional[Settings] = None, http_cli: Optional[HttpClient] = None):
        self.settings = settings or default_settings
        self.http_client = http_cli or default_http_client
        self._cached_domain: Optional[str] = None
        self._cached_timestamp: float = 0.0

    @property
    def is_cache_valid(self) -> bool:
        """Returns True if the cached active domain is still within TTL."""
        if not self._cached_domain:
            return False
        elapsed_hours = (time.time() - self._cached_timestamp) / 3600.0
        return elapsed_hours < self.settings.DOMAIN_REFRESH_INTERVAL_HOURS

    def extract_domains_from_html(self, html_text: str) -> List[str]:
        """Extracts candidate domain URLs from HTML content."""
        candidates = set()
        soup = BeautifulSoup(html_text, "html.parser")
        
        # 1. Parse from <a> tags
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            parsed = urlparse(href)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                clean_url = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
                candidates.add(clean_url)

        # 2. Regex fallback for plain text links
        regex_matches = re.findall(r"https?://[a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+", html_text)
        for full_match in re.finditer(r"https?://[a-zA-Z0-9.-]+(?::\d+)?", html_text):
            candidate = full_match.group(0).rstrip("/.")
            parsed = urlparse(candidate)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                candidates.add(f"{parsed.scheme}://{parsed.netloc}")

        # Exclude the publish page host itself
        pub_parsed = urlparse(self.settings.PUBLISH_PAGE_URL)
        pub_host = pub_parsed.netloc.lower()

        valid_list = []
        for cand in candidates:
            cand_netloc = urlparse(cand).netloc.lower()
            if cand_netloc != pub_host and cand_netloc != "localhost" and not cand_netloc.endswith("google.com"):
                valid_list.append(cand)

        return sorted(list(valid_list))

    async def probe_single_domain(self, domain: str, timeout: float = 5.0) -> Tuple[str, bool, float]:
        """Probes a single candidate domain with HEAD or lightweight GET."""
        start_time = time.monotonic()
        client = await self.http_client.get_client()
        try:
            resp = await client.head(domain, timeout=timeout)
            if resp.status_code < 500:
                latency = time.monotonic() - start_time
                return domain, True, latency
        except Exception:
            pass

        # Fallback to GET if HEAD was not allowed/supported
        try:
            resp = await client.get(domain, timeout=timeout)
            if resp.status_code < 500:
                latency = time.monotonic() - start_time
                return domain, True, latency
        except Exception as exc:
            logger.debug(f"Domain probe failed for {domain}: {exc}")

        return domain, False, 999.0

    async def fetch_candidate_domains(self) -> List[str]:
        """Fetches the publish page and extracts all candidate domains."""
        try:
            logger.info(f"Fetching candidate domains from {self.settings.PUBLISH_PAGE_URL}...")
            resp = await self.http_client.get(self.settings.PUBLISH_PAGE_URL)
            if resp.status_code == 200:
                return self.extract_domains_from_html(resp.text)
            logger.warning(f"Publish page returned status {resp.status_code}")
        except Exception as exc:
            logger.error(f"Error fetching publish page {self.settings.PUBLISH_PAGE_URL}: {exc}")
        return []

    async def get_active_domain(self, force_refresh: bool = False) -> str:
        """Returns a verified, lowest-latency active mirror domain."""
        if not force_refresh and self.is_cache_valid and self._cached_domain:
            return self._cached_domain

        logger.info("Resolving active domain...")
        candidates = await self.fetch_candidate_domains()
        
        if not candidates:
            # If no candidates found from publish page, fallback to previous cache or publish page host
            if self._cached_domain:
                logger.warning(f"No candidate found, falling back to cached domain {self._cached_domain}")
                return self._cached_domain
            raise RuntimeError("Unable to discover any valid mirror domains from the publish page.")

        # Concurrently probe candidates
        probe_tasks = [self.probe_single_domain(cand) for cand in candidates]
        results = await asyncio.gather(*probe_tasks)

        alive_domains = [res for res in results if res[1]]
        if not alive_domains:
            if self._cached_domain:
                logger.warning("All newly probed domains failed, returning previous cache.")
                return self._cached_domain
            # Pick first candidate as best-effort fallback
            fallback = candidates[0]
            logger.warning(f"No probed domain responded successfully, fallback to candidate {fallback}")
            self._cached_domain = fallback
            self._cached_timestamp = time.time()
            return fallback

        # Sort by latency ascending
        alive_domains.sort(key=lambda item: item[2])
        best_domain = alive_domains[0][0]
        logger.info(f"Selected active domain: {best_domain} (latency: {alive_domains[0][2]*1000:.1f}ms)")
        
        self._cached_domain = best_domain
        self._cached_timestamp = time.time()
        return best_domain

    def mark_domain_dead(self, domain: Optional[str] = None) -> None:
        """Invalidates cache to force rediscovery on next request."""
        if domain is None or domain == self._cached_domain:
            logger.info(f"Invalidating cached domain {self._cached_domain}")
            self._cached_domain = None
            self._cached_timestamp = 0.0
