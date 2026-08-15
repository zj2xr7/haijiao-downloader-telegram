# 海角下载机器人 (Haijiao Downloader Telegram Bot) 实施计划 (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个基于 Telegram 机器人与 Python 异步流水线的自动化系统，实现海角社区动态域名探活、受保护文章排版抓取、加密多媒体流解密、Markdown 本地归档、Rclone 异步上传 OneDrive、VPS 防爆盘自适应清理以及 OpenList 分享链接生成。

**Architecture:** 采用轻量单进程异步事件驱动架构（Asyncio + Aiogram v3 + Post-level Pipeline + DiskGuard + Rclone Subprocess）。单帖作为流水线原子单位，下载解密完成后即刻进入后台上传队列，并通过实时磁盘空间监控实现自适应挂起与唤醒。

**Tech Stack:** Python 3.11, aiogram v3, httpx, pydantic-settings, beautifulsoup4, pycryptodome, rclone, ffmpeg, pytest, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-08-16-haijiao-telegram-downloader-design.md`

## Global Constraints

- 运行环境兼容：Python 3.10+，支持 Linux VPS 原生运行及 Docker 容器化部署
- 磁盘安全限制：当 VPS 临时目录所在分区可用空间低于 `MIN_FREE_DISK_GB`（默认 2GB）时，必须阻塞并挂起新帖下载，待后台上传完成并删除本地文件后自动唤醒
- 异常防护：单帖内某个媒体下载失败不应阻断整帖排版，在 `post.md` 中记录占位符并记录告警
- 鉴权机制：所有 Bot 操作必须经过 `ALLOWED_USER_IDS` 白名单拦截校验

---

### Task 1: 基础工程搭建、配置管理与工具模块

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `src/config.py`
- Create: `src/models.py`
- Create: `src/utils/__init__.py`
- Create: `src/utils/logger.py`
- Create: `src/utils/http_client.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `Settings` class in `src/config.py`: 加载环境变量并提供全局配置对象 `settings`
  - `HttpClient` in `src/utils/http_client.py`: 封装带有统一 UA、超时和重试的 `httpx.AsyncClient`
  - Pydantic 模型（`PostDetail`, `MediaItem`, `ContentSegment`, `AuthorSummary`, `AuthorPostItem`, `TaskResult`）在 `src/models.py`

- [ ] **Step 1: Write the failing test for configuration and models**

```python
# tests/test_config.py
import pytest
from src.config import Settings
from src.models import PostDetail, MediaItem, ContentSegment

def test_settings_default_values(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test_bot_token_123")
    monkeypatch.setenv("ALLOWED_USER_IDS", "111,222,333")
    settings = Settings()
    assert settings.BOT_TOKEN == "test_bot_token_123"
    assert settings.allowed_user_id_list == [111, 222, 333]
    assert settings.MIN_FREE_DISK_GB == 2.0
    assert settings.PUBLISH_PAGE_URL == "https://hjw2026.com"

def test_post_detail_model():
    item = MediaItem(
        media_type="image",
        remote_url="https://example.com/1.enc",
        relative_path="images/01.jpg"
    )
    post = PostDetail(
        post_id="1001",
        title="Test Post",
        author_id="u99",
        author_name="Alice",
        source_url="https://example.com/post/1001",
        content_segments=[
            ContentSegment(segment_type="text", text_content="Hello world"),
            ContentSegment(segment_type="image", media_item=item)
        ],
        total_images=1
    )
    assert post.post_id == "1001"
    assert len(post.content_segments) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 3: Implement requirements.txt, .env.example, src/config.py, src/models.py, src/utils/logger.py, and src/utils/http_client.py**

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example src/ tests/test_config.py
git commit -m "feat(config): setup dependencies, pydantic settings, models and http utils"
```

---

### Task 2: 动态域名探活解析模块 (`core/resolver.py`)

**Files:**
- Create: `src/core/__init__.py`
- Create: `src/core/resolver.py`
- Test: `tests/test_resolver.py`

**Interfaces:**
- Consumes: `Settings` from `src/config.py`, `HttpClient` from `src/utils/http_client.py`
- Produces: `DomainResolver.get_active_domain(force_refresh: bool = False) -> str`

- [ ] **Step 1: Write the failing test for DomainResolver**

```python
# tests/test_resolver.py
import pytest
import respx
import httpx
from src.core.resolver import DomainResolver
from src.config import Settings

@pytest.mark.asyncio
async def test_domain_resolver_from_publish_page():
    settings = Settings(
        BOT_TOKEN="fake",
        ALLOWED_USER_IDS="123",
        PUBLISH_PAGE_URL="https://hjw2026.com"
    )
    resolver = DomainResolver(settings=settings)
    
    # Mock 发布页 HTML
    html_content = """
    <html>
        <body>
            <a href="https://hj1.example.com">线路1</a>
            <a href="https://hj2.example.com">线路2</a>
            <a href="https://hjw2026.com">发布页</a>
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_resolver.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.resolver'`

- [ ] **Step 3: Implement DomainResolver in `src/core/resolver.py`**
  - 支持从发布页正则/BS4提取外链域名
  - 并发执行异步 HEAD/GET 探活
  - 缓存最优结果并在失败时自动重探

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_resolver.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/resolver.py tests/test_resolver.py
git commit -m "feat(resolver): implement dynamic domain probing and caching"
```

---

### Task 3: 帖子排版与作者主页解析抓取器 (`core/crawler.py`)

**Files:**
- Create: `src/core/crawler.py`
- Test: `tests/test_crawler.py`

**Interfaces:**
- Consumes: `DomainResolver`, `HttpClient`, `PostDetail`, `AuthorSummary`, `AuthorPostItem`
- Produces:
  - `HaijiaoCrawler.extract_id_from_url(url: str) -> tuple[str, str]` (返回 `('post'|'author', id)`)
  - `HaijiaoCrawler.fetch_post_detail(post_id: str) -> PostDetail`
  - `HaijiaoCrawler.fetch_author_summary(author_id: str) -> AuthorSummary`
  - `HaijiaoCrawler.fetch_author_posts(author_id: str, page: int) -> list[AuthorPostItem]`

- [ ] **Step 1: Write the failing test for HaijiaoCrawler**

```python
# tests/test_crawler.py
import pytest
from src.core.crawler import HaijiaoCrawler
from src.config import Settings

def test_extract_id_from_url():
    crawler = HaijiaoCrawler(settings=Settings(BOT_TOKEN="fake", ALLOWED_USER_IDS="123"))
    # 单帖 URL 测试
    url1 = "https://hjabc.com/post/details?pid=987654"
    kind1, target_id1 = crawler.extract_id_from_url(url1)
    assert kind1 == "post"
    assert target_id1 == "987654"
    
    # 纯数字 ID 输入
    kind2, target_id2 = crawler.extract_id_from_url("987654")
    assert kind2 == "post"
    assert target_id2 == "987654"
    
    # 作者 URL 测试
    url3 = "https://hjabc.com/user/home?uid=54321"
    kind3, target_id3 = crawler.extract_id_from_url(url3)
    assert kind3 == "author"
    assert target_id3 == "54321"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_crawler.py`
Expected: FAIL

- [ ] **Step 3: Implement HaijiaoCrawler in `src/core/crawler.py`**
  - 正则模式提取 URL/ID
  - 抓取帖子详情并解析正文图文排版段落列表（保留正文文字、图片节点和视频节点在文章中的相对插入顺序）
  - 抓取作者信息与分页帖子列表

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_crawler.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/crawler.py tests/test_crawler.py
git commit -m "feat(crawler): implement post and author extraction"
```

---

### Task 4: 多媒体流解密与媒体处理引擎 (`core/decryptor.py`)

**Files:**
- Create: `src/core/decryptor.py`
- Test: `tests/test_decryptor.py`

**Interfaces:**
- Consumes: `MediaItem`
- Produces:
  - `MediaDecryptor.decrypt_image(raw_bytes: bytes, key: bytes = None) -> bytes`
  - `MediaDecryptor.download_and_decrypt_image(media_item: MediaItem, output_file: Path) -> bool`
  - `MediaDecryptor.download_and_decrypt_video_m3u8(media_item: MediaItem, output_file: Path) -> bool`

- [ ] **Step 1: Write the failing test for MediaDecryptor**

```python
# tests/test_decryptor.py
import pytest
from pathlib import Path
from src.core.decryptor import MediaDecryptor

def test_image_header_validation_and_decrypt(tmp_path):
    decryptor = MediaDecryptor()
    # 模拟标准 JPEG Magic Header (0xFF, 0xD8, 0xFF)
    valid_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 50
    assert decryptor.is_valid_image(valid_jpeg) is True
    
    # 模拟带混淆头或简单 XOR 加密的图片
    key = 0x5A
    obfuscated = bytes([b ^ key for b in valid_jpeg])
    decrypted = decryptor.decrypt_xor(obfuscated, key)
    assert decrypted[:3] == b"\xff\xd8\xff"
    assert decryptor.is_valid_image(decrypted) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_decryptor.py`
Expected: FAIL

- [ ] **Step 3: Implement MediaDecryptor in `src/core/decryptor.py`**
  - 支持图片流式下载、混淆头修复/AES解密与合法格式校验
  - 支持 HLS/M3U8 AES-128 TS 分片并发拉取、解密与合并封装为标准 MP4

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_decryptor.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/decryptor.py tests/test_decryptor.py
git commit -m "feat(decryptor): implement image and HLS AES-128 video decryption"
```

---

### Task 5: Markdown 排版生成器 (`core/renderer.py`)

**Files:**
- Create: `src/core/renderer.py`
- Test: `tests/test_renderer.py`

**Interfaces:**
- Consumes: `PostDetail`
- Produces:
  - `MarkdownRenderer.render_post_markdown(post: PostDetail) -> str`
  - `MarkdownRenderer.prepare_post_directory(post: PostDetail, base_dir: Path) -> Path`

- [ ] **Step 1: Write the failing test for MarkdownRenderer**

```python
# tests/test_renderer.py
from pathlib import Path
from src.core.renderer import MarkdownRenderer
from src.models import PostDetail, MediaItem, ContentSegment

def test_markdown_rendering(tmp_path):
    renderer = MarkdownRenderer()
    post = PostDetail(
        post_id="888",
        title="Test Title",
        author_id="u12",
        author_name="Bob",
        publish_time="2026-08-15 12:00:00",
        source_url="https://example.com/post/888",
        content_segments=[
            ContentSegment(segment_type="text", text_content="First paragraph."),
            ContentSegment(
                segment_type="image",
                media_item=MediaItem(media_type="image", remote_url="http://a.com/1.jpg", relative_path="images/01.jpg")
            ),
            ContentSegment(segment_type="text", text_content="Second paragraph."),
            ContentSegment(
                segment_type="video",
                media_item=MediaItem(media_type="video", remote_url="http://a.com/1.m3u8", relative_path="videos/01.mp4")
            )
        ]
    )
    md_text = renderer.render_post_markdown(post)
    assert "# Test Title" in md_text
    assert "First paragraph." in md_text
    assert "![图片 1](./images/01.jpg)" in md_text
    assert "Second paragraph." in md_text
    assert '<video controls src="./videos/01.mp4" width="100%"></video>' in md_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_renderer.py`
Expected: FAIL

- [ ] **Step 3: Implement MarkdownRenderer in `src/core/renderer.py`**
  - 格式化 YAML Frontmatter
  - 按顺序遍历 `content_segments` 生成排版
  - 创建并清理单帖目标目录结构

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_renderer.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/renderer.py tests/test_renderer.py
git commit -m "feat(renderer): implement Markdown layout renderer"
```

---

### Task 6: 磁盘自适应守护者 (DiskGuard) 与 Rclone/OpenList 执行器

**Files:**
- Create: `src/core/disk_guard.py`
- Create: `src/core/uploader.py`
- Test: `tests/test_disk_guard.py`
- Test: `tests/test_uploader.py`

**Interfaces:**
- Consumes: `Settings`, `PostDetail`
- Produces:
  - `DiskGuard.check_free_space_gb(path: Path) -> float`
  - `DiskGuard.acquire_download_slot() -> None` (当空间充足时通过，不足时异步阻塞)
  - `DiskGuard.release_download_slot() -> None`
  - `DiskGuard.notify_disk_freed() -> None`
  - `RcloneUploader.upload_and_cleanup(local_dir: Path, remote_subpath: str) -> tuple[bool, str]`
  - `RcloneUploader.get_openlist_url(author_folder: str, post_folder: str) -> str`

- [ ] **Step 1: Write the failing tests for DiskGuard and RcloneUploader**

```python
# tests/test_disk_guard.py
import pytest
from src.core.disk_guard import DiskGuard
from src.config import Settings

@pytest.mark.asyncio
async def test_disk_guard_capacity_check(tmp_path):
    settings = Settings(BOT_TOKEN="fake", ALLOWED_USER_IDS="1", MIN_FREE_DISK_GB=0.001)
    guard = DiskGuard(settings=settings, watch_dir=tmp_path)
    free_gb = guard.get_free_space_gb()
    assert free_gb > 0
    # 模拟申请通过
    can_proceed = await guard.can_download_now()
    assert can_proceed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_disk_guard.py`
Expected: FAIL

- [ ] **Step 3: Implement DiskGuard and RcloneUploader**
  - `disk_guard.py`: 基于 `shutil.disk_usage` 与 `asyncio.Event` 的自适应挂起唤醒
  - `uploader.py`: 基于 `asyncio.create_subprocess_exec` 执行 `rclone copy`，成功后执行 `shutil.rmtree` 彻底释放磁盘空间，并根据 `OPENLIST_BASE_URL` 规则拼接 URL。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_disk_guard.py tests/test_uploader.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/disk_guard.py src/core/uploader.py tests/test_disk_guard.py tests/test_uploader.py
git commit -m "feat(pipeline): implement DiskGuard and Rclone OpenList uploader"
```

---

### Task 7: 双工流水线任务调度管理器 (`core/pipeline.py`)

**Files:**
- Create: `src/core/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `HaijiaoCrawler`, `MediaDecryptor`, `MarkdownRenderer`, `DiskGuard`, `RcloneUploader`
- Produces:
  - `PipelineManager.submit_single_post(post_id: str, progress_callback: Callable = None) -> TaskResult`
  - `PipelineManager.submit_author_batch(author_id: str, pages: list[int], progress_callback: Callable = None) -> AsyncGenerator[TaskResult]`

- [ ] **Step 1: Write the failing test for PipelineManager**

```python
# tests/test_pipeline.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from src.core.pipeline import PipelineManager
from src.models import PostDetail, TaskStage

@pytest.mark.asyncio
async def test_pipeline_single_post_execution(tmp_path):
    mock_crawler = MagicMock()
    mock_crawler.fetch_post_detail = AsyncMock(return_value=PostDetail(
        post_id="111",
        title="Sample",
        author_id="a1",
        author_name="Author1",
        source_url="http://example.com/111"
    ))
    mock_decryptor = MagicMock()
    mock_renderer = MagicMock()
    mock_renderer.prepare_post_directory = MagicMock(return_value=tmp_path / "post_dir")
    mock_renderer.render_post_markdown = MagicMock(return_value="# Sample")
    
    mock_disk_guard = MagicMock()
    mock_disk_guard.acquire_download_slot = AsyncMock()
    mock_disk_guard.release_download_slot = MagicMock()
    mock_disk_guard.notify_disk_freed = MagicMock()
    
    mock_uploader = MagicMock()
    mock_uploader.upload_and_cleanup = AsyncMock(return_value=(True, ""))
    mock_uploader.get_openlist_url = MagicMock(return_value="https://pan.example.com/view/111")
    
    pipeline = PipelineManager(
        crawler=mock_crawler,
        decryptor=mock_decryptor,
        renderer=mock_renderer,
        disk_guard=mock_disk_guard,
        uploader=mock_uploader
    )
    
    result = await pipeline.process_single_post("111")
    assert result.stage == TaskStage.COMPLETED
    assert result.openlist_url == "https://pan.example.com/view/111"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline.py`
Expected: FAIL

- [ ] **Step 3: Implement PipelineManager in `src/core/pipeline.py`**
  - 编排「检查磁盘 $\rightarrow$ 抓取元数据 $\rightarrow$ 解密资源 $\rightarrow$ 渲染 Markdown $\rightarrow$ 提交后台上传 $\rightarrow$ 触发清理与空间唤醒」的双工流水线

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): implement full duplex download upload pipeline coordinator"
```

---

### Task 8: Telegram Bot 交互层实现 (Aiogram v3)

**Files:**
- Create: `src/bot/__init__.py`
- Create: `src/bot/middlewares/__init__.py`
- Create: `src/bot/middlewares/auth.py`
- Create: `src/bot/keyboards/__init__.py`
- Create: `src/bot/keyboards/inline.py`
- Create: `src/bot/handlers/__init__.py`
- Create: `src/bot/handlers/base.py`
- Create: `src/bot/handlers/download.py`
- Create: `src/bot/bot_app.py`
- Test: `tests/test_bot_auth.py`

**Interfaces:**
- Consumes: `Settings`, `PipelineManager`, `HaijiaoCrawler`
- Produces:
  - `AuthMiddleware`: 拦截非白名单用户
  - `create_bot_app()`: 创建并配置带有路由与状态机的 `Dispatcher` & `Bot` 实例

- [ ] **Step 1: Write the failing test for Bot Auth Middleware**

```python
# tests/test_bot_auth.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.bot.middlewares.auth import AuthMiddleware
from src.config import Settings

@pytest.mark.asyncio
async def test_auth_middleware_blocks_unauthorized_user():
    settings = Settings(BOT_TOKEN="fake", ALLOWED_USER_IDS="100,200")
    middleware = AuthMiddleware(settings=settings)
    
    event = MagicMock()
    event.from_user.id = 999  # 未授权用户
    event.answer = AsyncMock()
    
    handler = AsyncMock()
    res = await middleware(handler, event, {})
    
    assert res is None
    handler.assert_not_called()
    event.answer.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_auth.py`
Expected: FAIL

- [ ] **Step 3: Implement Bot Auth, Keyboards, Handlers, and Bot App**
  - `auth.py`: 白名单检查
  - `inline.py`: 作者页分页选择按钮组生成
  - `base.py`: `/start`, `/help`, `/status`
  - `download.py`: 处理 URL 监听、单帖直接启动、作者页分页选择交互（FSM 状态机）
  - `bot_app.py`: 初始化与组装

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bot_auth.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bot/ tests/test_bot_auth.py
git commit -m "feat(bot): implement aiogram bot handlers, auth middleware and page selector"
```

---

### Task 9: 统一入口、容器化与端到端集成测试

**Files:**
- Create: `src/main.py`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `README.md`
- Test: `tests/test_end_to_end_mock.py`

**Interfaces:**
- Produces:
  - `python src/main.py`: 生产启动入口
  - 完整的容器化构建与运行文件

- [ ] **Step 1: Write end-to-end mock integration test**

```python
# tests/test_end_to_end_mock.py
import pytest
from src.config import Settings
from src.core.resolver import DomainResolver
from src.core.crawler import HaijiaoCrawler
from src.core.decryptor import MediaDecryptor
from src.core.renderer import MarkdownRenderer
from src.core.disk_guard import DiskGuard
from src.core.uploader import RcloneUploader
from src.core.pipeline import PipelineManager

@pytest.mark.asyncio
async def test_full_system_wiring_mock(tmp_path):
    settings = Settings(
        BOT_TOKEN="fake_token_for_test",
        ALLOWED_USER_IDS="12345",
        TEMP_DOWNLOAD_DIR=str(tmp_path / "downloads"),
        MIN_FREE_DISK_GB=0.001
    )
    resolver = DomainResolver(settings=settings)
    crawler = HaijiaoCrawler(settings=settings, resolver=resolver)
    decryptor = MediaDecryptor()
    renderer = MarkdownRenderer()
    disk_guard = DiskGuard(settings=settings, watch_dir=tmp_path)
    uploader = RcloneUploader(settings=settings)
    
    pipeline = PipelineManager(
        crawler=crawler,
        decryptor=decryptor,
        renderer=renderer,
        disk_guard=disk_guard,
        uploader=uploader
    )
    assert pipeline is not None
```

- [ ] **Step 2: Run test to verify**

Run: `pytest tests/test_end_to_end_mock.py`
Expected: PASS

- [ ] **Step 3: Implement `src/main.py`, `Dockerfile`, `docker-compose.yml`, and `README.md`**

- [ ] **Step 4: Run complete test suite**

Run: `pytest`
Expected: ALL PASS

- [ ] **Step 5: Final Commit**

```bash
git add src/main.py Dockerfile docker-compose.yml README.md tests/
git commit -m "feat(core): provide main entrypoint, docker setup and e2e tests"
```
