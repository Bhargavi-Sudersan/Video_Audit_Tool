"""Per-video PDF report endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..config import Settings, get_settings
from ..services.analysis_runner import run_full_analysis
from ..services.report_service import build_report_pdf
from ..services.storage import get_repository

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{video_id}.pdf")
def report_pdf(video_id: str, use_ai: bool = False, settings: Settings = Depends(get_settings)):
    try:
        payload, path = run_full_analysis(video_id, use_ai, settings)
    except FileNotFoundError:
        raise HTTPException(404, "Video not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    # Fold in the reviewer's saved record (manual checklist / comments) if any.
    review = None
    for r in get_repository(settings).list_reviews():
        if r.video_id == video_id:
            review = r.model_dump()
            break

    pdf = build_report_pdf(video_id, video_id, payload, local_video_path=path, review=review)
    safe = video_id.replace("/", "_").replace(" ", "_")
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report_{safe}.pdf"'},
    )
