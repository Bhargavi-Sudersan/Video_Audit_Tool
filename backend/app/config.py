"""Central configuration, loaded from environment variables / .env."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    app_name: str = "Video Audit & Quality Review"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # --- Storage backend selection ---
    # "google"  -> use Google Drive (videos) + Google Sheets (review data)
    # "demo"    -> use local sample videos + local JSON store (no creds needed)
    storage_backend: str = "demo"

    # --- Google integration ---
    # Path to a service-account JSON key OR rely on application-default creds.
    google_credentials_file: str = ""
    google_drive_folder_id: str = ""        # folder containing videos to review
    google_sheets_spreadsheet_id: str = ""  # spreadsheet storing review data
    google_sheets_reviews_tab: str = "Reviews"

    # --- Local / demo paths ---
    demo_video_dir: str = "./data/videos"
    local_store_file: str = "./data/reviews.json"
    frame_cache_dir: str = "./data/frame_cache"

    # --- AI (Claude API) ---
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"
    ai_max_frames: int = 8                  # frames sent to the vision model
    enable_ai: bool = True

    # --- Analysis tuning ---
    target_samples: int = 60

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_dirs(settings: Settings) -> None:
    for path in (settings.demo_video_dir, settings.frame_cache_dir):
        os.makedirs(path, exist_ok=True)
    store_dir = os.path.dirname(settings.local_store_file)
    if store_dir:
        os.makedirs(store_dir, exist_ok=True)
