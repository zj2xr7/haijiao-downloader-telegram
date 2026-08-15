"""
Configuration loader using YAML files (config.yaml) and Pydantic validation.
"""
import os
import yaml
from pathlib import Path
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class BotConfig(BaseModel):
    """Telegram Bot Settings."""
    token: str = Field(default="", description="Telegram Bot Token from @BotFather")
    allowed_user_ids: List[int] = Field(default_factory=list, description="Whitelist of allowed Telegram user IDs")


class NetworkConfig(BaseModel):
    """Network & Crawler Domain Probing Settings."""
    publish_page_url: str = Field(default="https://hjw2026.com", description="Address of mirror publish page")
    domain_refresh_interval_hours: int = Field(default=6, description="Interval in hours before re-probing domain")
    request_timeout_seconds: int = Field(default=30, description="HTTP timeout in seconds")
    max_download_concurrency: int = Field(default=2, description="Media download concurrency")


class StorageConfig(BaseModel):
    """Local Storage & Disk Guard Settings."""
    temp_download_dir: str = Field(default="./downloads_temp", description="Local temporary download path")
    min_free_disk_gb: float = Field(default=2.0, description="Minimum free disk space threshold in GB")


class RcloneConfig(BaseModel):
    """Rclone & Cloud Upload Settings."""
    config_path: str = Field(default="", description="Custom rclone.conf path")
    remote_dest: str = Field(default="onedrive:Media/Haijiao", description="Remote target path")
    max_upload_concurrency: int = Field(default=2, description="Max concurrent uploads")


class OpenListConfig(BaseModel):
    """OpenList Web Indexer URL Mapping Settings."""
    base_url: str = Field(default="https://pan.example.com", description="Base URL of OpenList website")
    mount_path: str = Field(default="/Media/Haijiao", description="OneDrive mount route in OpenList")


class Settings(BaseModel):
    """Global configuration aggregator supporting YAML loading."""
    bot: BotConfig = Field(default_factory=BotConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    rclone: RcloneConfig = Field(default_factory=RcloneConfig)
    openlist: OpenListConfig = Field(default_factory=OpenListConfig)

    def __init__(
        self,
        config_path: Optional[str] = None,
        **data: Any
    ):
        # 1. If explicit kwargs were provided with uppercase or flat names (backwards compatibility / testing)
        flat_data: Dict[str, Any] = {}
        
        # Load from YAML if file exists or path is given
        target_path = Path(config_path or os.environ.get("CONFIG_PATH", "config.yaml"))
        if target_path.exists() and target_path.is_file():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}
                    if isinstance(loaded, dict):
                        flat_data.update(loaded)
            except Exception as e:
                print(f"[WARN] Failed to read config file {target_path}: {e}")

        # 2. Allow override from data kwargs
        for k, v in data.items():
            if k == "bot" and isinstance(v, (dict, BotConfig)):
                flat_data["bot"] = v
            elif k == "network" and isinstance(v, (dict, NetworkConfig)):
                flat_data["network"] = v
            elif k == "storage" and isinstance(v, (dict, StorageConfig)):
                flat_data["storage"] = v
            elif k == "rclone" and isinstance(v, (dict, RcloneConfig)):
                flat_data["rclone"] = v
            elif k == "openlist" and isinstance(v, (dict, OpenListConfig)):
                flat_data["openlist"] = v
            # Flat uppercase / legacy argument mappings
            elif k == "BOT_TOKEN":
                flat_data.setdefault("bot", {})["token"] = v
            elif k == "ALLOWED_USER_IDS":
                if isinstance(v, str):
                    ids = [int(p.strip()) for p in v.split(",") if p.strip().isdigit()]
                    flat_data.setdefault("bot", {})["allowed_user_ids"] = ids
                elif isinstance(v, list):
                    flat_data.setdefault("bot", {})["allowed_user_ids"] = v
            elif k == "PUBLISH_PAGE_URL":
                flat_data.setdefault("network", {})["publish_page_url"] = v
            elif k == "DOMAIN_REFRESH_INTERVAL_HOURS":
                flat_data.setdefault("network", {})["domain_refresh_interval_hours"] = v
            elif k == "REQUEST_TIMEOUT_SECONDS":
                flat_data.setdefault("network", {})["request_timeout_seconds"] = v
            elif k == "MAX_DOWNLOAD_CONCURRENCY":
                flat_data.setdefault("network", {})["max_download_concurrency"] = v
            elif k == "TEMP_DOWNLOAD_DIR":
                flat_data.setdefault("storage", {})["temp_download_dir"] = v
            elif k == "MIN_FREE_DISK_GB":
                flat_data.setdefault("storage", {})["min_free_disk_gb"] = float(v)
            elif k == "RCLONE_CONFIG_PATH":
                flat_data.setdefault("rclone", {})["config_path"] = v
            elif k == "RCLONE_REMOTE_DEST":
                flat_data.setdefault("rclone", {})["remote_dest"] = v
            elif k == "MAX_UPLOAD_CONCURRENCY":
                flat_data.setdefault("rclone", {})["max_upload_concurrency"] = v
            elif k == "OPENLIST_BASE_URL":
                flat_data.setdefault("openlist", {})["base_url"] = v
            elif k == "OPENLIST_MOUNT_PATH":
                flat_data.setdefault("openlist", {})["mount_path"] = v
            else:
                flat_data[k] = v

        super().__init__(**flat_data)

    # Convenience properties for backwards compatibility
    @property
    def BOT_TOKEN(self) -> str:
        return self.bot.token

    @property
    def allowed_user_id_list(self) -> List[int]:
        return self.bot.allowed_user_ids

    @property
    def PUBLISH_PAGE_URL(self) -> str:
        return self.network.publish_page_url

    @property
    def DOMAIN_REFRESH_INTERVAL_HOURS(self) -> int:
        return self.network.domain_refresh_interval_hours

    @property
    def REQUEST_TIMEOUT_SECONDS(self) -> int:
        return self.network.request_timeout_seconds

    @property
    def MAX_DOWNLOAD_CONCURRENCY(self) -> int:
        return self.network.max_download_concurrency

    @property
    def TEMP_DOWNLOAD_DIR(self) -> str:
        return self.storage.temp_download_dir

    @property
    def MIN_FREE_DISK_GB(self) -> float:
        return self.storage.min_free_disk_gb

    @property
    def RCLONE_CONFIG_PATH(self) -> str:
        return self.rclone.config_path

    @property
    def RCLONE_REMOTE_DEST(self) -> str:
        return self.rclone.remote_dest

    @property
    def MAX_UPLOAD_CONCURRENCY(self) -> int:
        return self.rclone.max_upload_concurrency

    @property
    def OPENLIST_BASE_URL(self) -> str:
        return self.openlist.base_url

    @property
    def OPENLIST_MOUNT_PATH(self) -> str:
        return self.openlist.mount_path

    @property
    def temp_download_path(self) -> Path:
        """Resolved Path object for local temporary download directory."""
        path = Path(self.TEMP_DOWNLOAD_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


def load_settings(config_path: Optional[str] = None) -> Settings:
    """Loads and returns Settings instance from yaml file or defaults."""
    return Settings(config_path=config_path)


# Default singleton settings instance
settings = load_settings()
