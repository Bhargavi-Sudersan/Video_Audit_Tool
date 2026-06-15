"""Review submission, retrieval and export endpoints."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..config import Settings, get_settings
from ..models.schemas import ReviewRecord, ReviewStatus, ReviewSubmission
from ..services.storage import get_repository

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.get("", response_model=list[ReviewRecord])
def list_reviews(settings: Settings = Depends(get_settings)):
    return get_repository(settings).list_reviews()


@router.post("", response_model=ReviewRecord)
def submit_review(submission: ReviewSubmission, settings: Settings = Depends(get_settings)):
    record = ReviewRecord(**submission.model_dump(), status=ReviewStatus.completed)
    get_repository(settings).save_review(record)
    return record


@router.get("/export.csv")
def export_csv(settings: Settings = Depends(get_settings)):
    records = get_repository(settings).list_reviews()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["video_id", "video_name", "reviewer", "outcome",
                     "status", "score", "ai_summary", "comments", "updated_at"])
    for r in records:
        comments = " | ".join(
            (f"[{c.timestamp_sec}s] " if c.timestamp_sec is not None else "") + c.text
            for c in r.comments
        )
        writer.writerow([r.video_id, r.video_name, r.reviewer, r.outcome.value,
                         r.status.value, r.score if r.score is not None else "",
                         r.ai_summary, comments, r.updated_at])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=review_summaries.csv"},
    )
