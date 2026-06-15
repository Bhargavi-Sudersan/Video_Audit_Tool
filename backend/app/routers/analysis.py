"""AI-assisted defect analysis endpoints."""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException

from ..config import Settings, get_settings
from ..services.analysis_runner import run_full_analysis

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# Simple in-process cache so repeated dashboard / panel reads are cheap.
_cache: dict[str, dict] = {}
_lock = threading.Lock()


@router.post("/{video_id}")
def analyze(
    video_id: str,
    use_ai: bool = False,
    force: bool = False,
    settings: Settings = Depends(get_settings),
):
    """Run defect analysis on a video.

    The local OpenCV detection (blur / black / frozen) always runs and is
    free. The paid Claude vision pass runs only when ``use_ai=true`` AND a
    key is configured server-side — this is the per-video toggle exposed in
    the UI so reviewers control token spend.
    """
    cache_key = f"{video_id}:{use_ai}"
    with _lock:
        if not force and cache_key in _cache:
            return _cache[cache_key]

    try:
        payload, _ = run_full_analysis(video_id, use_ai, settings)
    except FileNotFoundError:
        raise HTTPException(404, "Video not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    with _lock:
        _cache[cache_key] = payload
        _cache[video_id] = payload  # latest-result alias for GET-on-mount
    return payload


@router.get("/{video_id}")
def get_cached(video_id: str):
    with _lock:
        if video_id not in _cache:
            raise HTTPException(404, "No analysis cached. POST to run analysis first.")
        return _cache[video_id]
