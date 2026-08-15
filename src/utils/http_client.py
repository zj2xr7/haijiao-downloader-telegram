"""
Asynchronous HTTP client wrapper with retries and default browser headers.
"""
from typing import Optional, Dict, Any
import httpx
from src.utils.logger import logger


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class HttpClient:
    """Async HTTP Client managing persistent connection pool, realistic headers and retries."""

    def __init__(self, timeout: float = 30.0, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        """Returns or creates the underlying httpx AsyncClient."""
        if self._client is None or self._client.is_closed:
            headers = {
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://hjw2026.com/",
            }
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
                verify=False
            )
        return self._client

    async def get(self, url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        """Sends an async GET request with automatic retry."""
        client = await self.get_client()
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.get(url, headers=headers, params=params)
                return response
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_error = exc
                logger.warning(f"HTTP GET failed on {url} (attempt {attempt}/{self.max_retries}): {exc}")
        raise last_error or RuntimeError(f"Failed to GET {url}")

    async def head(self, url: str, headers: Optional[Dict[str, str]] = None) -> httpx.Response:
        """Sends an async HEAD request."""
        client = await self.get_client()
        return await client.head(url, headers=headers)

    async def close(self) -> None:
        """Closes the underlying client session."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Default singleton instance
http_client = HttpClient()
