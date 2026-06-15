"""Batch review endpoints (whole-folder or multi-video runs)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..services import batch_service
from ..services.storage import get_repository
from ..utils.drive_utils import parse_drive_id

router = APIRouter(prefix="/api/batch", tags=["batch"])


class BatchRequest(BaseModel):
    video_ids: list[str] | None = None     # explicit selection, OR
    folder: str | None = None              # a Drive folder link/id (all videos)
    use_ai: bool = False


@router.post("")
def start(req: BatchRequest, settings: Settings = Depends(get_settings)):
    repo = get_repository(settings)

    # Resolve the set of videos to review.
    folder_id = parse_drive_id(req.folder) if req.folder else None
    try:
        all_videos = {v.id: v for v in repo.list_videos(folder_id)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    if req.video_ids:
        selected = [all_videos[i] for i in req.video_ids if i in all_videos]
    else:
        selected = list(all_videos.values())

    if not selected:
        raise HTTPException(400, "No videos to review.")

    items = [{"id": v.id, "name": v.name} for v in selected]
    job = batch_service.start_batch(items, req.use_ai, settings)
    return job.to_dict()


@router.get("/{job_id}")
def status(job_id: str):
    job = batch_service.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.to_dict()
