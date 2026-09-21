"""Image utilities: base64, download, ultra-fast OCR preprocessing."""
from __future__ import annotations
import base64
import io
import httpx
import cv2
import numpy as np
from PIL import Image

def b64_to_pil(b64: str) -> Image.Image:
    if "," in b64 and ";base64," in b64:
        b64 = b64.split(";base64,", 1)[1]
    raw = base64.b64decode(b64)
    return Image.open(io.BytesIO(raw)).convert("RGB")

def pil_to_b64(img: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode()

async def fetch_image(url: str, timeout: int = 20) -> Image.Image:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")

def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """x2 upscale + gray + CLAHE + denoise + adaptive threshold. Fast (<30ms)."""
    arr = np.array(img)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    if max(h, w) < 400:
        scale = 400 / max(h, w)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.bilateralFilter(gray, 5, 50, 50)
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 31, 10)
    return Image.fromarray(th)
