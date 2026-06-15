"""Video listing and streaming endpoints."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from ..config import Settings, get_settings
from ..models.schemas import VideoItem
from ..services.storage import GoogleRepository, get_repository
from ..utils.drive_utils import parse_drive_id

router = APIRouter(prefix="/api/videos", tags=["videos"])


@router.get("", response_model=list[VideoItem])
def list_videos(folder: str | None = None, settings: Settings = Depends(get_settings)):
    """List videos. `folder` may be a Google Drive folder link or bare ID;
    when omitted, falls back to the server-configured folder (google mode)
    or the local demo folder (demo mode)."""
    repo = get_repository(settings)
    folder_id = parse_drive_id(folder) if folder else None
    try:
        return repo.list_videos(folder_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/{video_id}/stream")
def stream_video(video_id: str, request: Request, settings: Settings = Depends(get_settings)):
    repo = get_repository(settings)

    # Google Drive: proxy-stream the bytes.
    if isinstance(repo, GoogleRepository):
        try:
            generator = repo.drive.stream(video_id)
        except Exception as exc:
            raise HTTPException(404, f"Video not found: {exc}")
        return StreamingResponse(generator, media_type="video/mp4")

    # Demo: serve the local file with HTTP range support for seeking.
    try:
        path = repo.local_path_for(video_id)
    except FileNotFoundError:
        raise HTTPException(404, "Video not found")
    return _ranged_file_response(path, request)


def _ranged_file_response(path: str, request: Request):
    file_size = os.path.getsize(path)
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(path, media_type="video/mp4")

    try:
        units, rng = range_header.split("=")
        start_s, end_s = rng.split("-")
        start = int(start_s)
        end = int(end_s) if end_s else file_size - 1
    except ValueError:
        return FileResponse(path, media_type="video/mp4")

    end = min(end, file_size - 1)
    length = end - start + 1

    def iter_file():
        with open(path, "rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
    }
    return StreamingResponse(iter_file(), status_code=206,
                             media_type="video/mp4", headers=headers)
