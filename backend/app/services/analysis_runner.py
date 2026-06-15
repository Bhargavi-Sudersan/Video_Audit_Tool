"""Single source of truth for running a full analysis on one video.

Used by the analysis endpoint, the batch job runner and the PDF report
endpoint so the assembled payload never drifts between them.
"""
from __future__ import annotations

from ..config import Settings
from .ai_service import run_ai_analysis
from .storage import get_repository
from .video_analysis import analyze_video


def run_full_analysis(video_id: str, use_ai: bool, settings: Settings) -> tuple[dict, str]:
    """Return (payload, local_video_path). Raises FileNotFoundError / ValueError."""
    repo = get_repository(settings)
    path = repo.local_path_for(video_id)

    result = analyze_video(path, video_id=video_id, target_samples=settings.target_samples)
    ai = run_ai_analysis(path, result, settings, use_ai=use_ai)

    payload = result.to_dict()
    payload["ai"] = ai
    payload["ai_requested"] = use_ai
    payload["suggested_checklist"].update({
        "text_readability": ai["text_readability"],
        "logo_visibility": ai["logo_visibility"],
        "visual_clarity": ai["visual_clarity"]
        if ai["visual_clarity"] != "pass"
        else payload["suggested_checklist"].get("visual_clarity", "pass"),
    })
    payload["score"] = ai.get("score")
    return payload, path
