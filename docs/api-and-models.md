# 核心数据模型与接口规范 (Data Models & Interfaces)

本文档定义了系统中各层传递的数据模型（Pydantic Models / Dataclasses）与核心组件的异步接口规范。

---

## 1. 核心数据模型 (Data Models)

### 1.1 `PostMetadata` (帖子元数据)

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class MediaItem(BaseModel):
    media_type: str = Field(..., description="类型: 'image' 或 'video'")
    remote_url: str = Field(..., description="原始加密网络 URL")
    relative_path: str = Field(..., description="本地落盘相对路径，如 'images/01.jpg'")
    encryption_type: str = Field(default="none", description="加密算法: 'aes-128', 'header_xor', 'none'")
    key_url: Optional[str] = Field(default=None, description="密钥获取地址")
    iv_hex: Optional[str] = Field(default=None, description="初始化向量 IV 十六进制")

class ContentSegment(BaseModel):
    segment_type: str = Field(..., description="'text', 'image', 'video', 'quote', 'heading'")
    text_content: Optional[str] = None
    media_item: Optional[MediaItem] = None

class PostDetail(BaseModel):
    post_id: str
    title: str
    author_id: str
    author_name: str
    publish_time: Optional[str] = None
    source_url: str
    content_segments: List[ContentSegment] = Field(default_factory=list)
    total_images: int = 0
    total_videos: int = 0
```

### 1.2 `AuthorMetadata` (作者与分页信息)

```python
class AuthorSummary(BaseModel):
    author_id: str
    author_name: str
    avatar_url: Optional[str] = None
    total_posts: int = 0
    total_pages: int = 1

class AuthorPostItem(BaseModel):
    post_id: str
    title: str
    publish_time: Optional[str] = None
```

### 1.3 `TaskStatus` (流水线任务状态)

```python
from enum import Enum

class TaskStage(str, Enum):
    PENDING = "pending"          # 排队中
    RESOLVING = "resolving"      # 正在解析域名与帖子结构
    WAITING_DISK = "waiting_disk"# 等待磁盘空间可用
    DOWNLOADING = "downloading"  # 抓取与多媒体解密中
    RENDERING = "rendering"      # 生成 Markdown 与整理目录
    UPLOADING = "uploading"      # Rclone 上传至 OneDrive
    CLEANING = "cleaning"        # 本地清理中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败

class TaskResult(BaseModel):
    post_id: str
    title: str
    author_name: str
    stage: TaskStage
    openlist_url: Optional[str] = None
    error_message: Optional[str] = None
    elapsed_seconds: float = 0.0
```

---

## 2. 核心类接口规范 (Core Interfaces)

### 2.1 `DomainResolver` 接口

```python
class DomainResolver:
    async def get_active_domain(self, force_refresh: bool = False) -> str:
        """从发布页 https://hjw2026.com 探测并返回当前最优活跃域名"""
        ...
```

### 2.2 `HaijiaoCrawler` 接口

```python
class HaijiaoCrawler:
    async def parse_post_detail(self, post_id: str) -> PostDetail:
        """抓取并解析单篇帖子的图文排版及媒体加密信息"""
        ...

    async def get_author_info(self, author_id: str) -> AuthorSummary:
        """获取作者基本信息与总页数"""
        ...

    async def get_author_posts(self, author_id: str, page: int) -> List[AuthorPostItem]:
        """获取指定页码的帖子列表"""
        ...
```

### 2.3 `MediaDecryptor` 接口

```python
class MediaDecryptor:
    async def decrypt_image(self, remote_url: str, output_path: str) -> bool:
        """下载、流式解密图片并校验 Magic Header 后落盘"""
        ...

    async def decrypt_and_merge_video(self, m3u8_url: str, output_path: str) -> bool:
        """并发拉取 TS 分片与 AES-128 密钥，解密并合成 MP4"""
        ...
```

### 2.4 `DiskGuard` 接口

```python
class DiskGuard:
    async def acquire_slot(self) -> None:
        """检查 VPS 剩余容量；若不足 MIN_FREE_DISK_GB 则挂起等待"""
        ...

    def notify_space_freed(self) -> None:
        """当本地文件被删除后调用，唤醒等待中的任务"""
        ...
```

### 2.5 `Uploader & OpenList` 接口

```python
class RcloneUploader:
    async def upload_post_dir(self, local_dir: str, remote_subpath: str) -> bool:
        """调用 Rclone 异步上传本地帖子目录至 OneDrive"""
        ...

    def generate_openlist_url(self, author_folder: str, post_folder: str) -> str:
        """根据配置规则生成 OpenList Web 访问直达链接"""
        ...
```
