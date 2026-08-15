"""
Tests for DomainResolver.
"""
import pytest
import respx
import httpx
import base64
import hashlib
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

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


@pytest.mark.asyncio
async def test_domain_resolver_encrypted_app_config():
    settings = Settings(
        BOT_TOKEN="fake",
        ALLOWED_USER_IDS="123",
        PUBLISH_PAGE_URL="https://hjw2026.com"
    )
    http_cli = HttpClient()
    resolver = DomainResolver(settings=settings, http_cli=http_cli)

    config_data = {
        "domain": [
            {"name": "海角-线路一", "value": "https://agent.zswqqylip.cc"},
            {"name": "海角-线路二", "value": "https://aspect.zswqqylip.cc"}
        ],
        "backup_domain": [
            {"name": "海角-备用一", "value": "https://backup1.lvsuoesk.cc"}
        ]
    }
    raw_json = json.dumps(config_data).encode("utf-8")
    key_str = "0726001"
    key_hash = hashlib.sha256(key_str.encode("utf-8")).digest()
    iv = b"1234567890123456"
    cipher = AES.new(key_hash, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad(raw_json, AES.block_size))
    payload = base64.b64encode(iv + ciphertext).decode("utf-8")

    html_content = f"""
    <script>
        window.appConfig = {{
            data: "{payload}",
            key: "{key_str}"
        }};
    </script>
    <script>
        const line4Target = "d2g4tcjau6sbon.cloudfront.net";
    </script>
    """

    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get("https://hjw2026.com").mock(return_value=httpx.Response(200, text=html_content))
        respx_mock.head("https://agent.zswqqylip.cc").mock(return_value=httpx.Response(200))
        respx_mock.head("https://aspect.zswqqylip.cc").mock(return_value=httpx.Response(200))
        respx_mock.head("https://backup1.lvsuoesk.cc").mock(return_value=httpx.Response(200))
        respx_mock.head("https://d2g4tcjau6sbon.cloudfront.net").mock(return_value=httpx.Response(200))

        domains = resolver.extract_domains_from_html(html_content)
        assert "https://agent.zswqqylip.cc" in domains
        assert "https://aspect.zswqqylip.cc" in domains
        assert "https://backup1.lvsuoesk.cc" in domains
        assert "https://d2g4tcjau6sbon.cloudfront.net" in domains

        active = await resolver.get_active_domain(force_refresh=True)
        assert active in [
            "https://agent.zswqqylip.cc",
            "https://aspect.zswqqylip.cc",
            "https://backup1.lvsuoesk.cc",
            "https://d2g4tcjau6sbon.cloudfront.net"
        ]

    await http_cli.close()


def test_extract_domains_regex():
    resolver = DomainResolver()
    raw_text = "请访问最新地址：https://mirror1.hj.org 或 https://mirror2.hj.org 备用"
    domains = resolver.extract_domains_from_html(raw_text)
    assert "https://mirror1.hj.org" in domains
    assert "https://mirror2.hj.org" in domains
