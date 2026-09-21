"""Gap detection for sliders: GeeTest / Tencent / Binance / Temu / CutCaptcha / Capy.

100% local OpenCV, <50ms. Handles 2 cases:
 1. bg + piece provided -> template-match
 2. bg alone (dark hole) -> rectangular contour detection
"""
from __future__ import annotations
import cv2
import numpy as np
from PIL import Image

def _to_gray(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)

def find_slider_gap(bg: Image.Image, piece: Image.Image | None = None) -> tuple[int, float, int]:
    """Return (x_offset_px, confidence, bg_width). x in original image pixels."""
    gray_bg = _to_gray(bg)
    W = gray_bg.shape[1]
    if piece is not None:
        gray_p = _to_gray(piece)
        # normalize scales (the piece is often smaller)
        if gray_p.shape[0] > gray_bg.shape[0]:
            scale = gray_bg.shape[0] / gray_p.shape[0]
            gray_p = cv2.resize(gray_p, None, fx=scale, fy=scale)
        res = cv2.matchTemplate(cv2.Canny(gray_bg, 80, 200), cv2.Canny(gray_p, 80, 200), cv2.TM_CCOEFF_NORMED)
        _, conf, _, loc = cv2.minMaxLoc(res)
        return int(loc[0]), float(conf), W
    # Fallback: hole = dark rectangular zone + strong vertical edges
    edges = cv2.Canny(gray_bg, 60, 160)
    # ignore 15% gauche (position initiale du slider)
    x0 = int(W * 0.15)
    crop = edges[:, x0:]
    # vertical sum -> peak = hole edge
    col_sum = crop.sum(axis=0).astype(float)
    # smoothing
    col_sum = np.convolve(col_sum, np.ones(5) / 5, mode="same")
    x = int(np.argmax(col_sum)) + x0
    conf = float(min(1.0, col_sum.max() / (255 * gray_bg.shape[0] * 0.5)))
    return x, conf * 0.8, W

def find_slider_gap_best(bg: Image.Image, piece: Image.Image | None = None) -> tuple[int, float, int, str]:
    """Ensemble : OpenCV (deterministe) + ddddocr slide_match (confirme/precise).

    Retourne (x, conf, largeur, via). ddddocr ne remplace JAMAIS un resultat
    OpenCV confiant et eloigne (>12px) : il ne fait que confirmer/boost.
    """
    x, conf, w = find_slider_gap(bg, piece)
    via = "opencv"
    if piece is not None:
        try:
            from .dddd import slide_x
            dx, dc = slide_x(piece, bg)
            if dx is not None and abs(dx - x) <= 12:
                x = int(round((x + dx) / 2))
                conf = float(min(1.0, max(conf, dc) + 0.05))
                via = "opencv+ddddocr"
            elif dx is not None and conf < 0.25 and dc >= 0.6:
                x, conf, via = dx, float(dc * 0.9), "ddddocr"
        except Exception:
            pass
    return x, conf, w, via

def human_track(distance: int, seed: int | None = None) -> list[list[int]]:
    """Believable human trajectory (acceleration + micro-pauses + overshoot)."""
    import random
    rnd = random.Random(seed)
    track: list[list[int]] = []
    cur, v, t = 0.0, 0.0, 0
    mid = distance * rnd.uniform(0.6, 0.78)
    while cur < distance:
        a = 2.8 if cur < mid else -3.2
        v = max(0.6, v + a * rnd.uniform(0.8, 1.2))
        step = v * rnd.uniform(0.8, 1.25)
        cur = min(float(distance), cur + step)
        t += rnd.randint(12, 38)
        track.append([int(cur), t])
    # occasional human overshoot + correction
    if distance > 30 and rnd.random() < 0.6:
        over = rnd.randint(2, 6)
        track.append([distance + over, t + rnd.randint(40, 90)])
        track.append([distance, t + rnd.randint(90, 160)])
    return track
