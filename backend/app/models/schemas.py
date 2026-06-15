"""Pydantic models shared across the API."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Outcome(str, Enum):
    pass_ = "pass"
    fail = "fail"
    review = "review"


class ReviewStatus(str, Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"


class VideoItem(BaseModel):
    id: str
    name: str
    source: str                      # "google_drive" | "demo"
    size_bytes: int | None = None
    mime_type: str | None = None
    modified_time: str | None = None
    stream_url: str                  # backend endpoint to stream/preview


class ChecklistItem(BaseModel):
    key: str
    label: str
    status: Outcome = Outcome.review
    note: str = ""


DEFAULT_CHECKLIST: list[dict] = [
    {"key": "audio_sync", "label": "Audio synchronization"},
    {"key": "logo_visibility", "label": "Logo visibility"},
    {"key": "text_readability", "label": "Text readability"},
    {"key": "dropped_or_frozen_frames", "label": "Dropped or frozen frames"},
    {"key": "black_or_blank_frames", "label": "Black / blank frames"},
    {"key": "visual_clarity", "label": "Visual clarity (no blur)"},
]


class Comment(BaseModel):
    author: str = "reviewer"
    timestamp_sec: float | None = None     # video timestamp the comment refers to
    text: str
    created_at: str = Field(default_factory=_now)


class ReviewSubmission(BaseModel):
    video_id: str
    video_name: str
    reviewer: str = "reviewer"
    outcome: Outcome = Outcome.review
    checklist: list[ChecklistItem] = Field(default_factory=list)
    comments: list[Comment] = Field(default_factory=list)
    ai_summary: str = ""
    score: float | None = None


class ReviewRecord(ReviewSubmission):
    status: ReviewStatus = ReviewStatus.completed
    updated_at: str = Field(default_factory=_now)


class DashboardStats(BaseModel):
    total_videos: int
    reviewed_videos: int
    completion_pct: float
    passed: int
    failed: int
    needs_review: int
    recent: list[ReviewRecord] = Field(default_factory=list)
