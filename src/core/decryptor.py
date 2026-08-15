"""
Multimedia stream decryptor and format converter (AES-128 HLS & obfuscated images).
"""
import os
import re
import time
import shutil
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple, Callable, Any
from urllib.parse import urljoin

from Crypto.Cipher import AES
from src.models import MediaItem
from src.config import Settings, settings as default_settings
from src.utils.logger import logger
from src.utils.http_client import HttpClient, http_client as default_http_client


# Magic bytes for standard image formats
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
GIF_MAGIC_1 = b"GIF87a"
GIF_MAGIC_2 = b"GIF89a"
WEBP_MAGIC_PREFIX = b"RIFF"


class MediaDecryptor:
    """Handles downloading, decrypting, and assembling encrypted images and HLS videos."""

    def __init__(self, settings: Optional[Settings] = None, http_cli: Optional[HttpClient] = None):
        self.settings = settings or default_settings
        self.http_client = http_cli or default_http_client

    def is_valid_image(self, data: bytes) -> bool:
        """Checks if the byte stream starts with a recognized image magic header."""
        if not data or len(data) < 12:
            return False
        if data.startswith(JPEG_MAGIC):
            return True
        if data.startswith(PNG_MAGIC):
            return True
        if data.startswith(GIF_MAGIC_1) or data.startswith(GIF_MAGIC_2):
            return True
        if data.startswith(WEBP_MAGIC_PREFIX) and b"WEBP" in data[8:16]:
            return True
        return False

    def decrypt_xor(self, data: bytes, key: int) -> bytes:
        """Applies single-byte XOR decryption to data."""
        return bytes([b ^ key for b in data])

    def sanitize_image_bytes(self, raw_bytes: bytes) -> bytes:
        """
        Attempts to detect and restore obfuscated or masked image headers.
        """
        if self.is_valid_image(raw_bytes):
            return raw_bytes

        # Check if valid image header exists within the first 256 bytes (stripped prefix)
        for offset in range(1, min(256, len(raw_bytes) - 16)):
            candidate = raw_bytes[offset:]
            if self.is_valid_image(candidate):
                logger.debug(f"Found clean image header at offset {offset}")
                return candidate

        # Try common XOR keys if not clean
        for test_key in [0x5A, 0xA5, 0xFF, 0x88]:
            candidate = self.decrypt_xor(raw_bytes[:32], test_key)
            if self.is_valid_image(candidate):
                logger.debug(f"Image decoded successfully with XOR key 0x{test_key:02X}")
                return self.decrypt_xor(raw_bytes, test_key)

        return raw_bytes

    async def download_and_decrypt_image(self, media_item: MediaItem, output_file: Path) -> bool:
        """Downloads, decrypts, and saves an image to the target path."""
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Downloading image from {media_item.remote_url}...")
            resp = await self.http_client.get(media_item.remote_url)
            if resp.status_code == 200 and resp.content:
                clean_bytes = self.sanitize_image_bytes(resp.content)
                output_file.write_bytes(clean_bytes)
                media_item.download_success = True
                return True
            logger.warning(f"Failed to fetch image {media_item.remote_url}: status {resp.status_code}")
        except Exception as exc:
            logger.error(f"Error downloading image {media_item.remote_url}: {exc}")
        
        media_item.download_success = False
        return False

    def parse_m3u8_playlist(self, m3u8_text: str, base_url: str) -> Tuple[Optional[str], Optional[bytes], List[str]]:
        """
        Parses m3u8 playlist text to extract Key URL, IV, and absolute segment URLs.
        """
        key_url = None
        iv = None
        segments = []

        lines = [line.strip() for line in m3u8_text.splitlines() if line.strip()]
        for line in lines:
            if line.startswith("#EXT-X-KEY"):
                method_match = re.search(r"METHOD=([^,\s]+)", line)
                uri_match = re.search(r'URI="([^"]+)"', line)
                iv_match = re.search(r"IV=(0x[0-9a-fA-F]+)", line)

                if uri_match:
                    raw_uri = uri_match.group(1)
                    key_url = urljoin(base_url, raw_uri)
                if iv_match:
                    iv = bytes.fromhex(iv_match.group(1)[2:])
            elif not line.startswith("#"):
                seg_url = urljoin(base_url, line)
                segments.append(seg_url)

        return key_url, iv, segments

    async def fetch_ts_segment(
        self,
        client,
        seg_url: str,
        idx: int,
        on_segment_downloaded: Optional[Callable] = None
    ) -> Tuple[int, Optional[bytes]]:
        """Fetches a single TS video slice with retry."""
        content = None
        for _ in range(3):
            try:
                resp = await client.get(seg_url, timeout=25.0)
                if resp.status_code == 200:
                    content = resp.content
                    break
            except Exception:
                await asyncio.sleep(0.5)

        if on_segment_downloaded:
            try:
                on_segment_downloaded()
            except Exception:
                pass

        return idx, content

    async def download_and_decrypt_video_m3u8(
        self,
        media_item: MediaItem,
        output_file: Path,
        progress_callback: Optional[Callable[[int, int, str], Any]] = None
    ) -> bool:
        """
        Downloads HLS m3u8 playlist, fetches AES key, decrypts TS slices in parallel,
        and produces a consolidated MP4 file.
        """
        output_file.parent.mkdir(parents=True, exist_ok=True)
        raw_url = media_item.remote_url

        try:
            if not (".m3u8" in raw_url or "m3u8" in raw_url.lower()):
                logger.info(f"Downloading standard video file from {raw_url}...")
                if progress_callback:
                    await progress_callback(1, 1, "正在下载视频流...")
                resp = await self.http_client.get(raw_url)
                if resp.status_code == 200 and resp.content:
                    output_file.write_bytes(resp.content)
                    media_item.download_success = True
                    return True
                return False

            logger.info(f"Fetching m3u8 playlist from {raw_url}...")
            resp = await self.http_client.get(raw_url)
            if resp.status_code != 200:
                logger.error(f"Failed to fetch m3u8 from {raw_url}, status {resp.status_code}")
                return False

            key_url, iv_bytes, segment_urls = self.parse_m3u8_playlist(resp.text, raw_url)
            if not segment_urls:
                logger.warning(f"No video segments found in playlist: {raw_url}")
                return False

            total_segments = len(segment_urls)

            # Fetch key if AES-128 is specified
            key_bytes = None
            if key_url:
                logger.info(f"Fetching AES-128 key from {key_url}...")
                key_resp = await self.http_client.get(key_url)
                if key_resp.status_code == 200:
                    key_bytes = key_resp.content
                else:
                    logger.error(f"Failed to get key: {key_url}")
                    return False

            logger.info(f"Downloading {total_segments} video segments concurrently...")
            client = await self.http_client.get_client()

            # Progress tracking variables
            completed_segments = 0
            last_progress_time = 0.0

            def on_seg_done():
                nonlocal completed_segments
                completed_segments += 1

            async def progress_reporter():
                """Periodically updates progress callback during TS downloads."""
                nonlocal last_progress_time
                if not progress_callback:
                    return
                while completed_segments < total_segments:
                    now = time.monotonic()
                    if now - last_progress_time >= 1.5:
                        last_progress_time = now
                        pct = int((completed_segments / total_segments) * 100)
                        await progress_callback(
                            completed_segments,
                            total_segments,
                            f"下载视频分片 [{completed_segments}/{total_segments}] ({pct}%)"
                        )
                    await asyncio.sleep(0.5)

            reporter_task = None
            if progress_callback:
                reporter_task = asyncio.create_task(progress_reporter())

            try:
                tasks = [
                    self.fetch_ts_segment(client, seg_url, i, on_segment_downloaded=on_seg_done)
                    for i, seg_url in enumerate(segment_urls)
                ]
                segment_results = await asyncio.gather(*tasks)
            finally:
                if reporter_task:
                    reporter_task.cancel()

            # Final 100% callback
            if progress_callback:
                await progress_callback(
                    total_segments,
                    total_segments,
                    f"视频分片下载完毕 [{total_segments}/{total_segments}]，正在解密拼装..."
                )

            # Sort segments in order
            segment_results.sort(key=lambda x: x[0])
            
            temp_ts_path = output_file.with_suffix(".ts.temp")
            with open(temp_ts_path, "wb") as out_ts:
                for idx, chunk_bytes in segment_results:
                    if chunk_bytes is None:
                        logger.warning(f"Segment {idx} was missing or failed to download.")
                        continue

                    # Decrypt if key is available
                    if key_bytes:
                        seg_iv = iv_bytes or idx.to_bytes(16, byteorder="big")
                        cipher = AES.new(key_bytes, AES.MODE_CBC, seg_iv)
                        pad_len = len(chunk_bytes) % 16
                        if pad_len != 0:
                            chunk_bytes = chunk_bytes[:-pad_len]
                        try:
                            decrypted_ts = cipher.decrypt(chunk_bytes)
                            out_ts.write(decrypted_ts)
                        except Exception as dec_err:
                            logger.error(f"Error decrypting segment {idx}: {dec_err}")
                            out_ts.write(chunk_bytes)
                    else:
                        out_ts.write(chunk_bytes)

            # Convert/Transcode TS to MP4 using ffmpeg if available
            if shutil.which("ffmpeg"):
                logger.info("Converting decrypted TS to MP4 via ffmpeg...")
                if progress_callback:
                    await progress_callback(total_segments, total_segments, "FFmpeg 正在合并与转封装 MP4 视频...")
                cmd = [
                    "ffmpeg", "-y", "-i", str(temp_ts_path),
                    "-c", "copy", "-movflags", "faststart", str(output_file)
                ]
                proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if proc.returncode == 0 and output_file.exists():
                    temp_ts_path.unlink(missing_ok=True)
                    media_item.download_success = True
                    return True

            if temp_ts_path.exists() and temp_ts_path.stat().st_size > 0:
                shutil.move(str(temp_ts_path), str(output_file))
                media_item.download_success = True
                return True

        except Exception as exc:
            logger.error(f"Error processing video stream {raw_url}: {exc}")

        media_item.download_success = False
        return False
