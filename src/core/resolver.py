"""
Dynamic domain discovery and probing from the publishing page (https://hjw2026.com).
"""
import re
import time
import json
import base64
import hashlib
import asyncio
from typing import List, Optional, Tuple, Set
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from src.config import Settings, settings as default_settings
from src.utils.logger import logger
from src.utils.http_client import HttpClient, http_client as default_http_client


IGNORED_HOSTS = {
    "localhost", "127.0.0.1", "google.com", "699pic.com", "cloudflare.com",
    "cloudflareinsights.com", "schema.org", "w3.org", "favicon.ico"
}


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

    def decrypt_app_config_domains(self, html_text: str) -> List[str]:
        """
        Extracts and decrypts domain entries from encrypted window.appConfig.
        Structure: window.appConfig = { data: '...', key: '...' }
        AES-256-CBC, key = SHA256(key_str), IV = raw_bytes[:16]
        """
        extracted_domains = set()

        # Match window.appConfig = { data: "...", key: "..." }
        match_data = re.search(r'data\s*:\s*["\']([A-Za-z0-9+/=]+)["\']', html_text)
        match_key = re.search(r'key\s*:\s*["\']([^"\']+)["\']', html_text)

        if match_data and match_key:
            data_b64 = match_data.group(1)
            key_str = match_key.group(1)
            try:
                raw_bytes = base64.b64decode(data_b64)
                if len(raw_bytes) > 16:
                    iv = raw_bytes[:16]
                    ciphertext = raw_bytes[16:]
                    key_hash = hashlib.sha256(key_str.encode("utf-8")).digest()
                    cipher = AES.new(key_hash, AES.MODE_CBC, iv)
                    decrypted_raw = cipher.decrypt(ciphertext)
                    try:
                        decrypted_text = unpad(decrypted_raw, AES.block_size).decode("utf-8")
                    except Exception:
                        decrypted_text = decrypted_raw.decode("utf-8", errors="ignore")

                    config = json.loads(decrypted_text)
                    logger.debug(f"Successfully decrypted appConfig from publish page.")

                    # 1. Parse active domain list
                    for item in config.get("domain", []):
                        val = item.get("value") if isinstance(item, dict) else str(item)
                        if val:
                            extracted_domains.add(self._normalize_domain(val))

                    # 2. Parse backup domain list
                    for item in config.get("backup_domain", []):
                        val = item.get("value") if isinstance(item, dict) else str(item)
                        if val:
                            extracted_domains.add(self._normalize_domain(val))

            except Exception as exc:
                logger.warning(f"Failed to decrypt window.appConfig: {exc}")

        # Match line targets in inline scripts (e.g. line4Target = "d2g4tcjau6sbon.cloudfront.net")
        match_line4 = re.search(r'line4Target\s*=\s*["\']([^"\']+)["\']', html_text)
        if match_line4:
            line4_host = match_line4.group(1).strip()
            if line4_host:
                extracted_domains.add(self._normalize_domain(line4_host))

        return [d for d in extracted_domains if d]

    def _normalize_domain(self, raw_url: str) -> str:
        """Normalizes a domain string to http(s)://domain.com format."""
        raw_url = raw_url.strip().rstrip("/")
        if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
            raw_url = f"https://{raw_url}"
        parsed = urlparse(raw_url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".lower()
        return ""

    def extract_domains_from_html(self, html_text: str) -> List[str]:
        """Extracts candidate domain URLs from HTML content with decryption priority."""
        candidates: Set[str] = set()

        # 1. Priority: Decrypt from encrypted window.appConfig
        decrypted_domains = self.decrypt_app_config_domains(html_text)
        if decrypted_domains:
            candidates.update(decrypted_domains)

        # 2. Fallback: Parse from <a> tags and plain text links if no encrypted config
        if not candidates:
            soup = BeautifulSoup(html_text, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"].strip()
                normalized = self._normalize_domain(href)
                if normalized:
                    candidates.add(normalized)

            for full_match in re.finditer(r"https?://[a-zA-Z0-9.-]+(?::\d+)?", html_text):
                normalized = self._normalize_domain(full_match.group(0))
                if normalized:
                    candidates.add(normalized)

        # Exclude the publish page host and irrelevant static asset domains
        pub_parsed = urlparse(self.settings.PUBLISH_PAGE_URL)
        pub_host = pub_parsed.netloc.lower()

        valid_list = []
        for cand in candidates:
            cand_netloc = urlparse(cand).netloc.lower()
            if (
                cand_netloc
                and cand_netloc != pub_host
                and not any(ignored in cand_netloc for ignored in IGNORED_HOSTS)
            ):
                valid_list.append(cand)

        return sorted(list(set(valid_list)))

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
                domains = self.extract_domains_from_html(resp.text)
                logger.info(f"Extracted {len(domains)} candidate mirror domains: {domains}")
                return domains
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
