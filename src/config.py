"""
Global configuration loader using Pydantic Settings.
"""
from typing import List
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Application runtime settings and environment variable bindings."""
    
    # Telegram Bot
    BOT_TOKEN: str = Field(default="", description="Telegram Bot API Token")
    ALLOWED_USER_IDS: str = Field(default="", description="Comma-separated Telegram user IDs allowed to use the bot")
    
    # Publish Page & Network
    PUBLISH_PAGE_URL: str = Field(default="https://hjw2026.com", description="Address of the mirror list publishing page")
    DOMAIN_REFRESH_INTERVAL_HOURS: int = Field(default=6, description="Hours before forcing a fresh probe of active domain")
    REQUEST_TIMEOUT_SECONDS: int = Field(default=30, description="HTTP request timeout in seconds")
    MAX_DOWNLOAD_CONCURRENCY: int = Field(default=2, description="Maximum concurrent media chunk downloads")
    
    # Local Storage & Disk Guard
    TEMP_DOWNLOAD_DIR: str = Field(default="./downloads_temp", description="Local temporary path for files before upload")
    MIN_FREE_DISK_GB: float = Field(default=2.0, description="Minimum free disk space in GB required to start a new download")
    
    # Rclone & Remote Storage
    RCLONE_CONFIG_PATH: str = Field(default="", description="Path to rclone.conf (optional)")
    RCLONE_REMOTE_DEST: str = Field(default="onedrive:Media/Haijiao", description="Remote target path in Rclone format")
    MAX_UPLOAD_CONCURRENCY: int = Field(default=2, description="Max concurrent upload jobs")
    
    # OpenList
    OPENLIST_BASE_URL: str = Field(default="https://pan.example.com", description="Base URL of OpenList instance")
    OPENLIST_MOUNT_PATH: str = Field(default="/Media/Haijiao", description="Mount path of OneDrive inside OpenList")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def allowed_user_id_list(self) -> List[int]:
        """Parsed list of allowed Telegram user IDs."""
        if not self.ALLOWED_USER_IDS:
            return []
        ids = []
        for part in self.ALLOWED_USER_IDS.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        return ids

    @property
    def temp_download_path(self) -> Path:
        """Resolved Path object for local temporary download directory."""
        path = Path(self.TEMP_DOWNLOAD_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


# Singleton default settings instance
settings = Settings()
