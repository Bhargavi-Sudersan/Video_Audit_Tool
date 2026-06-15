"""
AI-assisted analysis using the Claude vision API.

The local OpenCV pass (``video_analysis``) is cheap and deterministic but
cannot reason about *semantic* quality: is on-screen text actually
readable? Is the brand logo present and clear? This service sends a small,
intelligently chosen set of frames to Claude's vision model and asks for a
structured assessment, which we merge into the suggested checklist.

Frame budget is strictly bounded (``ai_max_frames``) to keep cost and
latency predictable regardless of video length.
"""
from __future__ import annotations

import base64
import json

import cv2
import numpy as np

from ..config import Settings
from .video_analysis import AnalysisResult

SYSTEM_PROMPT = (
    "You are a meticulous video quality-assurance assistant for an "
    "educational and marketing media team. You are shown a handful of "
    "frames sampled from a single video. Assess on-screen quality only "
    "from what is visible. Respond with STRICT JSON and no prose."
)

USER_INSTRUCTION = (
    "Assess these sampled frames and return JSON exactly matching this schema:\n"
    "{\n"
    '  "text_readability": "pass|fail|review",\n'
    '  "logo_visibility": "pass|fail|review",\n'
    '  "visual_clarity": "pass|fail|review",\n'
    '  "score": <integer 0-100 overall visual quality>,\n'
    '  "summary": "<two-sentence plain-language summary of issues>",\n'
    '  "frame_notes": [{"frame": <int>, "note": "<short note>"}]\n'
    "}\n"
    "Use 'review' when genuinely uncertain. Be concise."
)


def _select_ai_frames(result: AnalysisResult, max_frames: int) -> list[int]:
    """Prefer frames near detected defects; fill the rest with even spread."""
    defect_frames = [f.frame_index for f in result.findings]
    chosen: list[int] = []
    seen: set[int] = set()
    for idx in defect_frames:
        if idx not in seen:
            chosen.append(idx)
            seen.add(idx)
        if len(chosen) >= max_frames:
            return sorted(chosen)

    if result.total_frames > 0:
        spread = np.linspace(0, result.total_frames - 1,
                             num=min(max_frames, result.total_frames), dtype=int)
        for idx in spread:
            idx = int(idx)
            if idx not in seen:
                chosen.append(idx)
                seen.add(idx)
            if len(chosen) >= max_frames:
                break
    return sorted(chosen)


def _encode_frame(frame: np.ndarray, max_dim: int = 768) -> str | None:
    h, w = frame.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    if scale < 1.0:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return None
    return base64.b64encode(buf.tobytes()).decode("ascii")


def run_ai_analysis(
    video_path: str,
    result: AnalysisResult,
    settings: Settings,
    use_ai: bool = True,
) -> dict:
    """Return a dict with AI checklist suggestions, score and summary.

    Falls back to a deterministic stub (no API call, no token spend) when:
      * the caller opts out via ``use_ai=False`` (the per-video UI toggle),
      * AI is disabled server-side, or
      * no API key is configured.
    This keeps the app fully functional and free unless AI is explicitly
    requested *and* a key is available.
    """
    if not use_ai or not settings.enable_ai or not settings.anthropic_api_key:
        return _offline_fallback(result)

    frame_indices = _select_ai_frames(result, settings.ai_max_frames)
    cap = cv2.VideoCapture(video_path)
    blocks: list[dict] = [{"type": "text", "text": USER_INSTRUCTION}]
    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        b64 = _encode_frame(frame)
        if not b64:
            continue
        blocks.append({"type": "text", "text": f"Frame index {idx}:"})
        blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })
    cap.release()

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.ai_model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": blocks}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        parsed = _safe_json(text)
        if parsed:
            return _normalize(parsed)
    except Exception as exc:  # network / auth / parse — degrade gracefully
        fallback = _offline_fallback(result)
        fallback["summary"] = f"AI analysis unavailable ({exc}). " + fallback["summary"]
        return fallback

    return _offline_fallback(result)


def _safe_json(text: str) -> dict | None:
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _normalize(parsed: dict) -> dict:
    allowed = {"pass", "fail", "review"}
    def clean(v: str) -> str:
        v = str(v).lower().strip()
        return v if v in allowed else "review"
    return {
        "text_readability": clean(parsed.get("text_readability", "review")),
        "logo_visibility": clean(parsed.get("logo_visibility", "review")),
        "visual_clarity": clean(parsed.get("visual_clarity", "review")),
        "score": int(parsed.get("score", 70)) if str(parsed.get("score", "")).strip().lstrip("-").isdigit() else 70,
        "summary": str(parsed.get("summary", "")).strip()[:600],
        "frame_notes": parsed.get("frame_notes", [])[:20],
        "ai_used": True,
    }


def _offline_fallback(result: AnalysisResult) -> dict:
    """Heuristic summary used when the AI API is not configured."""
    counts = result.defect_counts
    parts = [f"{n} {k.replace('_', ' ')}" for k, n in counts.items() if n]
    summary = (
        "Heuristic-only analysis (AI disabled). "
        + ("Detected: " + ", ".join(parts) + "." if parts else "No visual defects detected in sampled frames.")
    )
    blur = counts.get("blurry_frame", 0)
    return {
        "text_readability": "review",
        "logo_visibility": "review",
        "visual_clarity": "fail" if blur >= 3 else ("review" if blur else "pass"),
        "score": max(0, 100 - 10 * sum(counts.values())),
        "summary": summary,
        "frame_notes": [],
        "ai_used": False,
    }
