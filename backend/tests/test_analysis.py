"""Smoke test: generate a synthetic video with known defects and assert
the analysis engine flags them. Run with: pytest backend/tests
"""
import os
import tempfile

import cv2
import numpy as np

from app.services.video_analysis import analyze_video


def _make_video(path: str):
    w, h, fps = 320, 240, 10
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    def frame(t, blur=0):
        img = np.full((h, w, 3), 40, np.uint8)
        cv2.putText(img, f"F{t}", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        # add noise so non-defect frames have real texture / motion
        img = cv2.add(img, (np.random.rand(h, w, 3) * 40).astype(np.uint8))
        return img

    def sharp_pattern():
        # high-contrast scene: stays high-std even after a moderate blur,
        # so it reads as *blurry* (low focus) rather than *blank* (flat).
        img = np.zeros((h, w, 3), np.uint8)
        for i in range(0, w, 40):
            cv2.rectangle(img, (i, 0), (i + 20, h), (255, 255, 255), -1)
        cv2.putText(img, "DETAIL", (40, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 180, 255), 3)
        return img

    for t in range(20):
        out.write(frame(t))
    for _ in range(10):                     # black segment
        out.write(np.zeros((h, w, 3), np.uint8))
    frozen = frame(999)
    for _ in range(15):                     # frozen segment
        out.write(frozen)
    blurred = cv2.GaussianBlur(sharp_pattern(), (0, 0), 4)
    for _ in range(15):                     # blurry segment (high-contrast)
        # tiny per-frame jitter so they are not flagged as frozen too
        jitter = cv2.add(blurred, (np.random.rand(h, w, 3) * 6).astype(np.uint8))
        out.write(jitter)
    out.release()


def test_detects_core_defects():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "v.mp4")
        _make_video(path)
        result = analyze_video(path, video_id="v", target_samples=80)
        counts = result.defect_counts
        assert counts.get("black_frame", 0) > 0, "should detect black frames"
        assert counts.get("frozen_frame", 0) > 0, "should detect frozen frames"
        assert counts.get("blurry_frame", 0) > 0, "should detect blurry frames"
        assert result.suggested_outcome in {"fail", "review"}
