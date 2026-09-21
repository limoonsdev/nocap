"""Rotate / Click: 100% local OpenCV + existing detector."""
from __future__ import annotations
import cv2
import numpy as np
from PIL import Image

def estimate_rotation_angle(img: Image.Image) -> tuple[float, float]:
    """Estimate the required rotation angle (0-360). Fast heuristic:
    maximizes vertical symmetry + bottom-edge horizontality after rotation.
    Returns (angle_deg, confidence)."""
    gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    gray = cv2.resize(gray, (128, 128))
    best_a, best_s = 0.0, -1.0
    edges0 = cv2.Canny(gray, 60, 160)
    h, w = gray.shape
    for a in range(0, 360, 10):
        M = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
        rot = cv2.warpAffine(edges0, M, (w, h))
        # score = bottom-half edge energy ("upright" object = horizontal edges at bottom)
        bottom = rot[h // 2:, :].sum()
        top = rot[:h // 2, :].sum()
        score = float(bottom - top * 0.5)
        if score > best_s:
            best_s, best_a = score, float(a)
    # refine to ±5°
    refined = best_a
    best_s2 = best_s
    for a in [best_a - 7, best_a - 3, best_a + 3, best_a + 7]:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), a % 360, 1.0)
        rot = cv2.warpAffine(edges0, M, (w, h))
        s = float(rot[h // 2:, :].sum() - rot[:h // 2, :].sum() * 0.5)
        if s > best_s2:
            best_s2, refined = s, float(a % 360)
    conf = float(min(1.0, max(0.1, best_s2 / (255 * 64 * 64))))
    # angle to apply to straighten = (360 - refined) % 360
    return (360 - refined) % 360, conf * 0.7 + 0.2

def click_targets(img: Image.Image, target_en: str, grid: int = 3) -> tuple[list[list[int]], float, str]:
    """Split the image into grid x grid, score each cell with LocalDetector.
    Returns (coords_0_1000, confidence, via). Cell centers of matched cells.
    Fallback: ddddocr generic object boxes (unlabeled) as low-confidence candidates."""
    from .detector import LocalDetector
    det = LocalDetector("auto")
    w, h = img.size
    out: list[list[int]] = []
    confs: list[float] = []
    cw, ch = w / grid, h / grid
    for gy in range(grid):
        for gx in range(grid):
            cell = img.crop((int(gx * cw), int(gy * ch), int((gx + 1) * cw), int((gy + 1) * ch)))
            match, conf = det.contains(cell, target_en)
            if match:
                # 0-1000 relative coords (captcha standard)
                cx = int((gx + 0.5) / grid * 1000)
                cy = int((gy + 0.5) / grid * 1000)
                out.append([cx, cy])
                confs.append(conf)
    if out:
        return out, float(sum(confs) / len(confs)), "grid-detector"
    try:
        from .dddd import detect_boxes
        boxes = detect_boxes(img)
        if boxes:
            pts = [[int((b[0] + b[2]) / 2 / w * 1000),
                    int((b[1] + b[3]) / 2 / h * 1000)] for b in boxes[:9]]
            return pts, 0.45, "ddddocr-det"
    except Exception:
        pass
    return [], 0.0, "none"
