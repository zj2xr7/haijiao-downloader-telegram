"""
Tests for DomainResolver.
"""
import pytest
import respx
import httpx
from src.core.resolver import DomainResolver
from src.config import Settings
from src.utils.http_client import HttpClient


@pytest.mark.asyncio
async def test_domain_resolver_from_publish_page():
    settings = Settings(
        BOT_TOKEN="fake",
        ALLOWED_USER_IDS="123",
        PUBLISH_PAGE_URL="https://hjw2026.com"
    )
    http_cli = HttpClient()
    resolver = DomainResolver(settings=settings, http_cli=http_cli)
    
    html_content = """
    <html>
        <body>
            <h1>海角发布页</h1>
            <a href="https://hj1.example.com">国内线路1</a>
            <a href="https://hj2.example.com">海外线路2</a>
            <a href="https://hjw2026.com">永久发布页</a>
        </body>
    </html>
    """
    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get("https://hjw2026.com").mock(return_value=httpx.Response(200, text=html_content))
        respx_mock.head("https://hj1.example.com").mock(return_value=httpx.Response(200))
        respx_mock.head("https://hj2.example.com").mock(return_value=httpx.Response(200))
        
        domain = await resolver.get_active_domain(force_refresh=True)
        assert domain in ["https://hj1.example.com", "https://hj2.example.com"]
        assert domain != "https://hjw2026.com"
        
        # Test cache validity
        assert resolver.is_cache_valid is True
        
        # Test mark dead
        resolver.mark_domain_dead(domain)
        assert resolver.is_cache_valid is False
    
    await http_cli.close()


def test_extract_domains_regex():
    resolver = DomainResolver()
    raw_text = "请访问最新地址：https://mirror1.hj.org 或 https://mirror2.hj.org 备用"
    domains = resolver.extract_domains_from_html(raw_text)
    assert "https://mirror1.hj.org" in domains
    assert "https://mirror2.hj.org" in domains
