"""
Local (no-AI) video defect detection using OpenCV.

These are fast, deterministic, CPU-only heuristics that run on the sampled
frames produced by ``frame_sampler``. They flag the four core defect
classes the review checklist cares about:

  * blurry frames      -> variance of the Laplacian (focus measure)
  * black / blank       -> mean luminance + low contrast
  * duplicate / frozen  -> near-zero difference vs the previous sampled frame
  * (text presence is handled by the AI service; here we surface low-detail
     frames that are candidates for "unreadable text" review)

Each detected issue carries a frame index, timestamp, severity and a short
human-readable message so the UI can render timestamp-anchored findings.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import cv2
import numpy as np

from .frame_sampler import SamplingPlan, build_sampling_plan

# --- Tunable thresholds (exposed so teams can calibrate per content type) ---
BLUR_VARIANCE_THRESHOLD = 100.0     # below this Laplacian variance => blurry
BLACK_LUMA_THRESHOLD = 16.0         # mean luma (0-255) below this => black
BLANK_STD_THRESHOLD = 8.0           # luma std below this => flat / blank
FROZEN_DIFF_THRESHOLD = 0.15        # mean abs diff below this => frozen/dup
                                    # (truly duplicated frames decode to ~0;
                                    #  low-motion talking-head/slide content
                                    #  still produces 0.3+ so is not flagged)


@dataclass
class FrameFinding:
    frame_index: int
    timestamp: float
    defect_type: str
    severity: str            # "low" | "medium" | "high"
    score: float
    message: str


@dataclass
class AnalysisResult:
    video_id: str
    total_frames: int
    duration_sec: float
    fps: float
    resolution: str
    sampled_frames: int
    findings: list[FrameFinding] = field(default_factory=list)
    defect_counts: dict[str, int] = field(default_factory=dict)
    suggested_outcome: str = "pass"           # pass | review | fail
    suggested_checklist: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["findings"] = [asdict(f) if not isinstance(f, dict) else f for f in self.findings]
        return d


def _laplacian_variance(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _severity_from_ratio(ratio: float) -> str:
    if ratio >= 0.66:
        return "high"
    if ratio >= 0.33:
        return "medium"
    return "low"


def analyze_video(
    video_path: str,
    video_id: str,
    target_samples: int = 60,
) -> AnalysisResult:
    """Run the full local defect-detection pass over a video."""
    plan: SamplingPlan = build_sampling_plan(video_path, target_samples=target_samples)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    findings: list[FrameFinding] = []
    prev_small: np.ndarray | None = None
    prev_index: int | None = None

    for idx in plan.frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue

        ts = plan.index_to_timestamp(idx)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_luma = float(gray.mean())
        std_luma = float(gray.std())

        # --- black / blank ---
        if mean_luma < BLACK_LUMA_THRESHOLD:
            findings.append(FrameFinding(
                idx, ts, "black_frame", "high", round(mean_luma, 2),
                f"Near-black frame (mean luminance {mean_luma:.1f}/255).",
            ))
        elif std_luma < BLANK_STD_THRESHOLD:
            findings.append(FrameFinding(
                idx, ts, "blank_frame", "medium", round(std_luma, 2),
                f"Flat / blank frame (luma std {std_luma:.1f}).",
            ))
        else:
            # --- blur (skip on black frames; they are trivially low-variance) ---
            lap_var = _laplacian_variance(gray)
            if lap_var < BLUR_VARIANCE_THRESHOLD:
                ratio = 1.0 - (lap_var / BLUR_VARIANCE_THRESHOLD)
                findings.append(FrameFinding(
                    idx, ts, "blurry_frame", _severity_from_ratio(ratio),
                    round(lap_var, 2),
                    f"Possible blur (focus measure {lap_var:.0f} < {BLUR_VARIANCE_THRESHOLD:.0f}).",
                ))

        # --- duplicate / frozen (compare consecutive *sampled* frames) ---
        small = cv2.resize(gray, (128, 128))
        if prev_small is not None and prev_index is not None:
            diff = float(np.mean(cv2.absdiff(small, prev_small)))
            # Only meaningful when the two samples are temporally close.
            close = (idx - prev_index) <= max(int(plan.fps), 1) * 2
            if close and diff < FROZEN_DIFF_THRESHOLD:
                findings.append(FrameFinding(
                    idx, ts, "frozen_frame", "medium", round(diff, 3),
                    f"Frozen / duplicate frame vs previous sample (diff {diff:.2f}).",
                ))
        prev_small = small
        prev_index = idx

    cap.release()

    counts: dict[str, int] = {}
    for f in findings:
        counts[f.defect_type] = counts.get(f.defect_type, 0) + 1

    resolution = f"{plan.width}x{plan.height}"
    result = AnalysisResult(
        video_id=video_id,
        total_frames=plan.total_frames,
        duration_sec=plan.duration_sec,
        fps=round(plan.fps, 2),
        resolution=resolution,
        sampled_frames=len(plan.frame_indices),
        findings=findings,
        defect_counts=counts,
    )
    result.suggested_checklist = _suggest_checklist(counts)
    result.suggested_outcome = _suggest_outcome(counts)
    return result


def _suggest_checklist(counts: dict[str, int]) -> dict[str, str]:
    """Map detected defects to a suggested pass/fail per checklist item."""
    return {
        "dropped_or_frozen_frames": "fail" if counts.get("frozen_frame", 0) else "pass",
        "black_or_blank_frames": "fail" if (counts.get("black_frame", 0) or counts.get("blank_frame", 0)) else "pass",
        "visual_clarity": "review" if counts.get("blurry_frame", 0) else "pass",
        # text_readability + logo + audio are AI / human assisted; default to review
        "text_readability": "review",
        "logo_visibility": "review",
        "audio_sync": "review",
    }


def _suggest_outcome(counts: dict[str, int]) -> str:
    high_impact = counts.get("black_frame", 0) + counts.get("frozen_frame", 0)
    medium_impact = counts.get("blurry_frame", 0) + counts.get("blank_frame", 0)
    if high_impact >= 2:
        return "fail"
    if high_impact >= 1 or medium_impact >= 3:
        return "review"
    return "pass"
