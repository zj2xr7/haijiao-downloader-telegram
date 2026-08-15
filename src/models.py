"""
Data models and type definitions for Haijiao Downloader.
"""
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class MediaItem(BaseModel):
    """Represents an image or video asset within a post."""
    media_type: str = Field(..., description="Type: 'image' or 'video'")
    remote_url: str = Field(..., description="Original network URL (often encrypted or HLS stream)")
    relative_path: str = Field(..., description="Local relative path (e.g. 'images/01.jpg' or 'videos/01.mp4')")
    encryption_type: str = Field(default="none", description="Encryption: 'aes-128', 'header_xor', or 'none'")
    key_url: Optional[str] = Field(default=None, description="URL for decryption key if required")
    iv_hex: Optional[str] = Field(default=None, description="Initialization vector (IV) in hex")
    download_success: bool = Field(default=False, description="Whether the media was successfully fetched and decrypted")


class ContentSegment(BaseModel):
    """Represents a segment of the post content in layout order."""
    segment_type: str = Field(..., description="'text', 'image', 'video', 'quote', 'heading'")
    text_content: Optional[str] = None
    media_item: Optional[MediaItem] = None


class PostDetail(BaseModel):
    """Full detail of a parsed post."""
    post_id: str
    title: str
    author_id: str
    author_name: str
    publish_time: Optional[str] = None
    source_url: str
    content_segments: List[ContentSegment] = Field(default_factory=list)
    total_images: int = 0
    total_videos: int = 0


class AuthorSummary(BaseModel):
    """Summary of an author page."""
    author_id: str
    author_name: str
    avatar_url: Optional[str] = None
    total_posts: int = 0
    total_pages: int = 1


class AuthorPostItem(BaseModel):
    """Brief metadata for a single post on an author's list."""
    post_id: str
    title: str
    publish_time: Optional[str] = None


class TaskStage(str, Enum):
    """Lifecycle stages of a single post download and upload pipeline."""
    PENDING = "pending"
    RESOLVING = "resolving"
    WAITING_DISK = "waiting_disk"
    DOWNLOADING = "downloading"
    RENDERING = "rendering"
    UPLOADING = "uploading"
    CLEANING = "cleaning"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskResult(BaseModel):
    """Outcome report for a completed or failed post processing task."""
    post_id: str
    title: str
    author_name: str
    stage: TaskStage
    openlist_url: Optional[str] = None
    error_message: Optional[str] = None
    elapsed_seconds: float = 0.0
    downloaded_images: int = 0
    downloaded_videos: int = 0
