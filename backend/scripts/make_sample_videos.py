"""Generate sample videos for demo mode so the library is populated on first run.

Usage:
    python -m scripts.make_sample_videos            # writes to ./data/videos
"""
import os

import cv2
import numpy as np

OUT_DIR = os.environ.get("DEMO_VIDEO_DIR", "./data/videos")
W, H, FPS = 640, 360, 24


def _writer(name: str):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    return cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H)), path


def _scene(t: int, label: str):
    img = np.full((H, W, 3), 28, np.uint8)
    # moving gradient panel
    x = (t * 6) % W
    cv2.rectangle(img, (x, 60), (x + 160, 300), (60, 120, 90), -1)
    cv2.rectangle(img, (24, 24), (120, 70), (40, 200, 180), -1)   # "logo"
    cv2.putText(img, "BRAND", (30, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (10, 30, 28), 2)
    cv2.putText(img, label, (40, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (235, 235, 235), 2)
    cv2.putText(img, f"t={t}", (40, 320), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 1)
    return img


def make_clean(name="01_clean_lecture.mp4", seconds=8):
    out, path = _writer(name)
    for t in range(FPS * seconds):
        out.write(_scene(t, "Intro to Algorithms"))
    out.release()
    print("wrote", path)


def make_defective(name="02_promo_with_defects.mp4", seconds=10):
    out, path = _writer(name)
    n = FPS * seconds
    for t in range(n):
        if 2 * FPS <= t < 3 * FPS:                 # 1s black-out
            out.write(np.zeros((H, W, 3), np.uint8))
        elif 5 * FPS <= t < 6 * FPS:               # 1s freeze
            out.write(_scene(5 * FPS, "Summer Sale"))
        elif 7 * FPS <= t < 8 * FPS:               # 1s blur
            out.write(cv2.GaussianBlur(_scene(t, "Summer Sale"), (0, 0), 5))
        else:
            out.write(_scene(t, "Summer Sale"))
    out.release()
    print("wrote", path)


if __name__ == "__main__":
    make_clean()
    make_defective()
