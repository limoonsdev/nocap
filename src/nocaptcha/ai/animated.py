"""Animated captchas (GIF / WebP / MP4): frame sampling + temporal vote."""
from __future__ import annotations
import io
from PIL import Image

def sample_animated_frames(raw: bytes, max_frames: int = 8) -> list[Image.Image]:
    """Extract up to max_frames evenly spread."""
    try:
        im = Image.open(io.BytesIO(raw))
    except Exception:
        return []
    frames: list[Image.Image] = []
    try:
        n = getattr(im, "n_frames", 1)
        if n <= 1:
            return [im.convert("RGB")]
        step = max(1, n // max_frames)
        for i in range(0, n, step)[:max_frames]:
            im.seek(i)
            frames.append(im.convert("RGB").copy())
    except Exception:
        frames = [im.convert("RGB")]
    return frames

def vote_frames(scores: list[tuple[bool, float]]) -> tuple[bool, float]:
    """Confidence-weighted majority vote. Fast and robust to temporal noise."""
    if not scores: return False, 0.0
    pos = sum(s for m, s in scores if m)
    neg = sum(s for m, s in scores if not m)
    total = pos + neg + 1e-9
    if pos >= neg:
        return True, pos / total
    return False, neg / total
