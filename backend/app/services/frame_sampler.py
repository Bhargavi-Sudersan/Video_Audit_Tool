"""
Intelligent frame sampling for large videos.

Instead of decoding every frame (expensive for long / high-resolution
videos), we sample frames using an adaptive strategy:

  * A baseline uniform grid of `target_samples` frames spread across the
    whole timeline guarantees coverage end-to-end.
  * On top of that we run a fast, low-cost "scan" pass that decodes a
    coarse stream of frames and flags moments of high or *suspiciously low*
    change (scene cuts, freezes, blackouts). Those interesting timestamps
    are added to the sample set so defects are not missed between grid
    points.

The output is a sorted, de-duplicated list of frame indices to analyse.
This keeps analysis cost roughly constant regardless of video length.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class SamplingPlan:
    frame_indices: list[int]
    total_frames: int
    fps: float
    duration_sec: float
    width: int
    height: int

    def index_to_timestamp(self, frame_index: int) -> float:
        if self.fps <= 0:
            return 0.0
        return round(frame_index / self.fps, 3)


def _probe(capture: cv2.VideoCapture) -> tuple[int, float, int, int]:
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    fps = float(capture.get(cv2.CAP_PROP_FPS)) or 0.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or 0
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 0
    return total, fps, width, height


def build_sampling_plan(
    video_path: str,
    target_samples: int = 60,
    scan_stride_sec: float = 1.0,
    change_sensitivity: float = 2.0,
) -> SamplingPlan:
    """Decide which frame indices to analyse.

    Args:
        video_path: local path to the video file.
        target_samples: size of the uniform baseline grid.
        scan_stride_sec: how often (seconds) the cheap scan pass samples.
        change_sensitivity: z-score threshold for flagging "interesting"
            moments during the scan pass.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    total, fps, width, height = _probe(cap)
    duration = (total / fps) if fps else 0.0

    # Some containers report 0 frames; fall back to a sequential read.
    if total <= 0:
        total = _count_frames(cap)
        duration = (total / fps) if fps else 0.0

    indices: set[int] = set()

    # 1) Uniform baseline grid.
    if total > 0:
        grid = np.linspace(0, max(total - 1, 0), num=min(target_samples, total), dtype=int)
        indices.update(int(i) for i in grid)

    # 2) Cheap scan pass to find scene changes / freezes / blackouts.
    if fps > 0 and total > 0:
        stride = max(int(scan_stride_sec * fps), 1)
        diffs: list[tuple[int, float]] = []
        prev_small: np.ndarray | None = None
        idx = 0
        while idx < total:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                break
            small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (64, 64))
            if prev_small is not None:
                diffs.append((idx, float(np.mean(cv2.absdiff(small, prev_small)))))
            prev_small = small
            idx += stride

        if diffs:
            values = np.array([d for _, d in diffs], dtype=np.float64)
            mean, std = values.mean(), values.std() or 1.0
            for (frame_idx, value) in diffs:
                z = abs(value - mean) / std
                # High change = scene cut; near-zero change = possible freeze.
                if z >= change_sensitivity or value < (mean * 0.1):
                    indices.add(int(frame_idx))

    cap.release()

    ordered = sorted(i for i in indices if 0 <= i < max(total, 1))
    if not ordered:
        ordered = [0]

    return SamplingPlan(
        frame_indices=ordered,
        total_frames=total,
        fps=fps,
        duration_sec=round(duration, 2),
        width=width,
        height=height,
    )


def _count_frames(cap: cv2.VideoCapture) -> int:
    count = 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    while True:
        ok, _ = cap.grab()
        if not ok:
            break
        count += 1
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    return count
