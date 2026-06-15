"""Dashboard analytics endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..models.schemas import DashboardStats, Outcome
from ..services.storage import get_repository

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardStats)
def dashboard(settings: Settings = Depends(get_settings)):
    repo = get_repository(settings)
    videos = repo.list_videos()
    reviews = repo.list_reviews()

    reviewed_ids = {r.video_id for r in reviews}
    total = len(videos)
    reviewed = len([v for v in videos if v.id in reviewed_ids]) or len(reviewed_ids)

    passed = len([r for r in reviews if r.outcome == Outcome.pass_])
    failed = len([r for r in reviews if r.outcome == Outcome.fail])
    needs = len([r for r in reviews if r.outcome == Outcome.review])

    completion = round((reviewed / total) * 100, 1) if total else 0.0
    recent = sorted(reviews, key=lambda r: r.updated_at, reverse=True)[:8]

    return DashboardStats(
        total_videos=total,
        reviewed_videos=reviewed,
        completion_pct=completion,
        passed=passed,
        failed=failed,
        needs_review=needs,
        recent=recent,
    )
