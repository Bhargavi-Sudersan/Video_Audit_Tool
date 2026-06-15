"""
Storage abstraction.

The rest of the app talks to a single ``Repository`` interface. Two
implementations are provided:

  * ``GoogleRepository`` — videos from Google Drive, reviews in Google Sheets.
  * ``DemoRepository``   — videos from a local folder, reviews in a JSON file.

This keeps cloud specifics isolated and makes it trivial to add new backends
(S3 + DynamoDB, Azure Blob + Cosmos, etc.) later — satisfying the modular /
scalable design goal.
"""
from __future__ import annotations

import json
import os
import threading

from .frame_sampler import build_sampling_plan  # noqa: F401 (re-export convenience)
from ..config import Settings
from ..models.schemas import ReviewRecord, VideoItem


class Repository:
    """Interface every storage backend implements."""

    def list_videos(self, folder_id: str | None = None) -> list[VideoItem]:
        raise NotImplementedError

    def local_path_for(self, video_id: str) -> str:
        """Return a local filesystem path to the video (download if needed)."""
        raise NotImplementedError

    def save_review(self, record: ReviewRecord) -> None:
        raise NotImplementedError

    def list_reviews(self) -> list[ReviewRecord]:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Demo backend (no credentials required)
# --------------------------------------------------------------------------- #
class DemoRepository(Repository):
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()

    def list_videos(self, folder_id: str | None = None) -> list[VideoItem]:
        out: list[VideoItem] = []
        d = self.settings.demo_video_dir
        if not os.path.isdir(d):
            return out
        for name in sorted(os.listdir(d)):
            if name.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".avi")):
                path = os.path.join(d, name)
                out.append(VideoItem(
                    id=name, name=name, source="demo",
                    size_bytes=os.path.getsize(path),
                    mime_type="video/mp4",
                    stream_url=f"/api/videos/{name}/stream",
                ))
        return out

    def local_path_for(self, video_id: str) -> str:
        path = os.path.join(self.settings.demo_video_dir, video_id)
        if not os.path.isfile(path):
            raise FileNotFoundError(video_id)
        return path

    def save_review(self, record: ReviewRecord) -> None:
        with self._lock:
            data = self._read()
            data[record.video_id] = json.loads(record.model_dump_json())
            tmp = self.settings.local_store_file + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp, self.settings.local_store_file)

    def list_reviews(self) -> list[ReviewRecord]:
        return [ReviewRecord(**v) for v in self._read().values()]

    def _read(self) -> dict:
        f = self.settings.local_store_file
        if not os.path.isfile(f):
            return {}
        try:
            with open(f) as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return {}


# --------------------------------------------------------------------------- #
# Google backend
# --------------------------------------------------------------------------- #
class GoogleRepository(Repository):
    def __init__(self, settings: Settings):
        from .drive_service import DriveService
        from .sheets_service import SheetsService

        self.settings = settings
        self.drive = DriveService(settings)
        self.sheets = SheetsService(settings)
        self._index: dict[str, dict] = {}

    def list_videos(self, folder_id: str | None = None) -> list[VideoItem]:
        files = self.drive.list_videos(folder_id)
        self._index = {f["id"]: f for f in files}
        return [
            VideoItem(
                id=f["id"], name=f["name"], source="google_drive",
                size_bytes=int(f["size"]) if f.get("size") else None,
                mime_type=f.get("mimeType"),
                modified_time=f.get("modifiedTime"),
                stream_url=f"/api/videos/{f['id']}/stream",
            )
            for f in files
        ]

    def local_path_for(self, video_id: str) -> str:
        os.makedirs(self.settings.frame_cache_dir, exist_ok=True)
        dest = os.path.join(self.settings.frame_cache_dir, f"{video_id}.video")
        if not os.path.isfile(dest):
            self.drive.download_to_path(video_id, dest)
        return dest

    def save_review(self, record: ReviewRecord) -> None:
        self.sheets.upsert(record)

    def list_reviews(self) -> list[ReviewRecord]:
        return [ReviewRecord(**r) for r in self.sheets.list_records()]


_repository: Repository | None = None


def get_repository(settings: Settings) -> Repository:
    global _repository
    if _repository is None:
        if settings.storage_backend == "google":
            _repository = GoogleRepository(settings)
        else:
            _repository = DemoRepository(settings)
    return _repository
