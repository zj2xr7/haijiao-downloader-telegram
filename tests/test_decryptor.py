"""
Tests for MediaDecryptor.
"""
import pytest
from pathlib import Path
from Crypto.Cipher import AES
from src.core.decryptor import MediaDecryptor
from src.models import MediaItem


def test_image_header_validation_and_decrypt():
    decryptor = MediaDecryptor()
    
    # 1. Standard JPEG header
    valid_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 50
    assert decryptor.is_valid_image(valid_jpeg) is True
    
    # 2. Standard PNG header
    valid_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 30
    assert decryptor.is_valid_image(valid_png) is True

    # 3. Stripped / Offset header
    obfuscated_with_garbage_prefix = b"JUNK_HEADER_12345" + valid_jpeg
    assert decryptor.is_valid_image(obfuscated_with_garbage_prefix) is False
    cleaned = decryptor.sanitize_image_bytes(obfuscated_with_garbage_prefix)
    assert decryptor.is_valid_image(cleaned) is True
    assert cleaned.startswith(b"\xff\xd8\xff")

    # 4. XOR masked image
    key = 0x5A
    xor_image = decryptor.decrypt_xor(valid_jpeg, key)
    assert decryptor.is_valid_image(xor_image) is False
    restored = decryptor.sanitize_image_bytes(xor_image)
    assert decryptor.is_valid_image(restored) is True


def test_parse_m3u8_playlist():
    decryptor = MediaDecryptor()
    m3u8_content = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:0
#EXT-X-KEY:METHOD=AES-128,URI="enc.key",IV=0x0123456789abcdef0123456789abcdef
#EXTINF:10.0,
seg0.ts
#EXTINF:10.0,
https://cdn.example.com/video/seg1.ts
#EXT-X-ENDLIST
"""
    base_url = "https://cdn.example.com/video/index.m3u8"
    key_url, iv_bytes, segments = decryptor.parse_m3u8_playlist(m3u8_content, base_url)
    
    assert key_url == "https://cdn.example.com/video/enc.key"
    assert iv_bytes == bytes.fromhex("0123456789abcdef0123456789abcdef")
    assert len(segments) == 2
    assert segments[0] == "https://cdn.example.com/video/seg0.ts"
    assert segments[1] == "https://cdn.example.com/video/seg1.ts"
