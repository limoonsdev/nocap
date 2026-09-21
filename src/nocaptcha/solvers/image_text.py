"""Generic image-select + text OCR solver — local AI core."""
from __future__ import annotations
import time
from PIL import Image
from .base import BaseSolver, SolverContext, SolverResult
from ..ai.detector import LocalDetector
from ..ai.ocr import LocalOcr
from ..ai.instructions import parse_instruction
from ..ai.animated import sample_animated_frames, vote_frames
from ..config import get_settings

_det, _ocr = None, None

def _lazy():
    global _det, _ocr
    s = get_settings()
    if _det is None: _det = LocalDetector(s.detector_backend)
    if _ocr is None: _ocr = LocalOcr(s.ocr_backend, s.ocr_langs)
    return _det, _ocr

class ImageSelectSolver(BaseSolver):
    name = "image-select"
    method = "YOLOv8n/CLIP + animated vote + FR/EN parsing"
    notes = "100% local, CPU, <150ms/image heuristic, ~40ms YOLO."

    async def solve_tiles(self, instruction: str, tiles: list[tuple[str | int, Image.Image | bytes]], animated: bool = False) -> SolverResult:
        t0 = time.time()
        det, _ = _lazy()
        parsed = parse_instruction(instruction)
        target = parsed["target_en"]
        selected, details = [], {}
        for tid, payload in tiles:
            if isinstance(payload, (bytes, bytearray)):
                frames = sample_animated_frames(bytes(payload)) if animated else []
                if not frames:
                    from io import BytesIO
                    frames = [Image.open(BytesIO(bytes(payload))).convert("RGB")]
            else:
                frames = [payload]
            scores = [det.contains(f, target) for f in frames]
            match, conf = vote_frames(scores) if len(scores) > 1 else scores[0]
            # MobileNet int8 bonus (3.6 MB) when cached: improves recall
            # on real photos, changes nothing otherwise (never downloads here).
            try:
                from ..ai.onnx_zoo import is_cached, mobilenet_contains
                if is_cached("mobilenetv2-12-int8"):
                    for f in frames:
                        m_match, m_conf = mobilenet_contains(f, target)
                        if m_match and m_conf > conf:
                            match, conf = True, float(max(conf, m_conf))
                            break
            except Exception:
                pass
            details[str(tid)] = {"match": match, "conf": round(conf, 3)}
            if match: selected.append(tid)
        ms = int((time.time() - t0) * 1000)
        return SolverResult(ok=True, selected_ids=selected, confidence=0.85, detail={"target": parsed, "per_tile": details}, ms=ms)

    async def solve(self, ctx: SolverContext) -> SolverResult:
        return SolverResult(ok=False, detail={"error": "use POST /v1/solve/image with instruction + tiles"}, ms=0)

class ImageTextSolver(BaseSolver):
    name = "image-text"
    method = "RapidOCR/EasyOCR/Tesseract + CLAHE preprocessing"
    notes = "Local multilingual OCR fr/en."

    async def solve_image(self, img: Image.Image, preprocess: bool = True) -> SolverResult:
        import time
        t0 = time.time()
        _, ocr = _lazy()
        text, conf = ocr.read(img, preprocess=preprocess)
        ms = int((time.time() - t0) * 1000)
        return SolverResult(ok=bool(text.strip()), text=text, confidence=conf, detail={"backend": ocr.active}, ms=ms)

    async def solve_pil(self, img: Image.Image, langs: str | None = None) -> SolverResult:
        """OCR-family compatible alias (per-request langs)."""
        import time
        t0 = time.time()
        s = get_settings()
        ocr = LocalOcr(s.ocr_backend, langs or s.ocr_langs)
        text, conf = ocr.read(img, preprocess=True)
        ms = int((time.time() - t0) * 1000)
        return SolverResult(ok=bool(text.strip()), text=text, confidence=conf,
                            detail={"backend": ocr.active}, ms=ms)

    async def solve(self, ctx: SolverContext) -> SolverResult:
        return SolverResult(ok=False, detail={"error": "use POST /v1/solve/ocr"}, ms=0)
