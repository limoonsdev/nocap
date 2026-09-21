"""Routes /v1/solve* — local API core (35+ types) + metrics + auto-learn.

- Unlimited API-side concurrency (wide semaphore 100, Playwright pool): 0 rate-limit.
- Every OK solve is measured (metrics.record -> average seconds) and captured
  (learn.save_capture) for auto-training.
- Bank recall before heavy inference (OCR/slider): <5ms on seen inputs.
- Universal contract: POST /v1/solve (JSON: image_b64 | image_url) or
  POST /v1/solve/file (multipart upload). `type` is always required.
"""
from __future__ import annotations
import asyncio
import base64
import io
import time
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from PIL import Image
from ..models import (
    SolveRequest, SolveResponse, ImageSolveRequest, OcrRequest,
    SliderRequest, RotateRequest, ClickRequest, PowRequest, MathRequest,
)
from ..solvers import REGISTRY
from ..solvers.base import SolverContext, SolverResult
from ..solvers.image_text import ImageSelectSolver, ImageTextSolver
from ..solvers.audio import AudioSolver
from ..utils.image import b64_to_pil, fetch_image
from .. import metrics as METRICS

router = APIRouter(prefix="/solve", tags=["solve"])

# 0 API rate-limit: wide memory guardrail, never a business quota
SEM = asyncio.Semaphore(100)

def _resp(result, type_: str) -> SolveResponse:
    return SolveResponse(ok=result.ok, type=type_, ms=result.ms, token=result.token,
                         coords=result.coords, selected_ids=result.selected_ids,
                         text=result.text, confidence=result.confidence, detail=result.detail)

async def _finish(type_: str, result: SolverResult, image_b64: str | None = None):
    """Universal post-processing: metrics + auto-capture (best-effort, never business-blocking)."""
    try:
        await METRICS.record(type_, result.ok, result.ms)
    except Exception:
        pass
    if result.ok and image_b64:
        try:
            from ..learn import save_capture
            sol: dict = {}
            if result.text: sol["text"] = result.text
            if result.coords: sol["coords"] = result.coords
            if result.token: sol["token"] = result.token[:120]
            if result.selected_ids is not None: sol["selected_ids"] = result.selected_ids
            save_capture(type_, image_b64, sol, ms=result.ms, conf=result.confidence)
        except Exception:
            pass
    # systematically enriched detail: perf recall + learn
    try:
        snap = await METRICS.snapshot()
        b = (snap.get("by_type") or {}).get(type_, {})
        if b:
            result.detail.setdefault("avg_s", b.get("avg_s"))
            result.detail.setdefault("success_rate", b.get("success"))
    except Exception:
        pass
    return _resp(result, type_)

def _ctx_from_req(req: SolveRequest) -> SolverContext:
    extra = dict(req.data or {})
    for k in ("challenge", "salt", "maxnumber", "algorithm", "instruction", "images",
              "bg_b64", "bg_url", "piece_b64", "appid", "capi_"):
        v = getattr(req, k, None) if hasattr(req, k) else None
        if v is not None:
            extra[k] = v
    if req.image_b64 and "bg_b64" not in extra and req.type.value in (
            "slider-captcha", "cutcaptcha", "capy-puzzle", "temu-captcha",
            "binance-captcha", "tencent-captcha", "arkose"):
        extra["bg_b64"] = req.image_b64
    if req.image_b64_2:
        extra["piece_b64"] = req.image_b64_2
    if req.instruction:
        extra["instruction"] = req.instruction
    return SolverContext(sitekey=req.sitekey, url=req.url, proxy=req.proxy,
                         timeout=req.timeout, enterprise=req.enterprise,
                         action=req.action, extra=extra)

def _recall_ocr(type_: str, img: Image.Image):
    # 1) GPU/CPU classifier trained on your captures (most accurate when available)
    try:
        from ..learn.trainer import predict_classifier
        txt, conf = predict_classifier(type_, img)
        if txt and conf >= 0.55:
            return SolverResult(ok=True, text=txt, confidence=float(conf),
                                detail={"via": "gpu-classifier", "recall_score": float(conf)}, ms=8)
    except Exception:
        pass
    # 2) template bank (hash + template-match, <5ms on seen inputs)
    try:
        from ..learn import recall
        hit = recall(type_, img)
        if hit and isinstance(hit.get("solution"), dict) and hit["solution"].get("text"):
            s = hit["solution"]
            return SolverResult(ok=True, text=s["text"], confidence=0.99,
                                detail={"via": hit.get("via", "recall"), "recall_score": hit.get("score")}, ms=3)
    except Exception:
        pass
    return None

@router.post("", response_model=SolveResponse, summary="Universal solver: 35+ types, single endpoint (JSON)")
async def solve_generic(req: SolveRequest):
    """Send `type` (required) + image via `image_b64` or `image_url`
    (or `sitekey`+`url` for browser tokens, `data.challenge` for PoW).
    Returns the answer: `text`, `coords`, `selected_ids` or `token`."""
    async with SEM:
        t0 = time.time()
        solver = REGISTRY.get(req.type.value)
        if not solver:
            raise HTTPException(404, f"unknown type: {req.type} — see /v1/capabilities")
        ctx = _ctx_from_req(req)
        try:
            t = req.type.value
            if t in ("normal-captcha", "text-captcha", "number-captcha", "russian-captcha",
                     "chinese-captcha", "amazon-captcha", "vk-captcha", "atb-captcha",
                     "math-captcha", "image-text") and (req.image_b64 or req.image_url):
                img = b64_to_pil(req.image_b64) if req.image_b64 else await fetch_image(req.image_url or "")
                hit = _recall_ocr(t, img)
                if hit:
                    hit.ms = int((time.time() - t0) * 1000)
                    return await _finish(t, hit, req.image_b64)
                res = await solver.solve_pil(img, req.langs)  # type: ignore
                return await _finish(t, res, req.image_b64)
            if t in ("slider-captcha", "cutcaptcha", "capy-puzzle", "temu-captcha",
                     "binance-captcha", "tencent-captcha", "arkose") and (req.image_b64 or req.image_url):
                from ..ai.slider import find_slider_gap_best, human_track
                bg = b64_to_pil(req.image_b64) if req.image_b64 else await fetch_image(req.image_url or "")
                piece = b64_to_pil(req.image_b64_2) if req.image_b64_2 else None
                x, conf, w, via = find_slider_gap_best(bg, piece)
                return await _finish(t, SolverResult(ok=conf > 0.15, coords=[x], confidence=conf,
                                          detail={"x": x, "width": w, "via": via, "track": human_track(x)},
                                          ms=int((time.time() - t0) * 1000)), req.image_b64)
            if t == "rotate-captcha" and (req.image_b64 or req.image_url):
                from ..ai.rotate_click import estimate_rotation_angle
                img = b64_to_pil(req.image_b64) if req.image_b64 else await fetch_image(req.image_url or "")
                angle, conf = estimate_rotation_angle(img)
                return await _finish(t, SolverResult(ok=True, coords=[int(angle)], confidence=conf,
                                          detail={"angle": angle}, ms=int((time.time() - t0) * 1000)), req.image_b64)
            if t == "click-captcha" and (req.image_b64 or req.image_url) and req.instruction:
                from ..ai.rotate_click import click_targets
                from ..ai.instructions import parse_instruction
                img = b64_to_pil(req.image_b64) if req.image_b64 else await fetch_image(req.image_url or "")
                parsed = parse_instruction(req.instruction)
                coords, conf, via = click_targets(img, parsed["target_en"])
                return await _finish(t, SolverResult(ok=bool(coords), coords=[c for p in coords for c in p],
                                          confidence=conf, detail={"points": coords, "via": via, "target": parsed},
                                          ms=int((time.time() - t0) * 1000)), req.image_b64)
            if t in ("altcha", "friendly-captcha", "captchafox", "prosopo-procaptcha") and req.data.get("challenge"):
                res = await solver.solve_pow(req.data.get("challenge", ""), req.data.get("salt", ""),  # type: ignore
                                             int(req.data.get("maxnumber", 100000)), req.data.get("algorithm", "SHA-256"))
                return await _finish(t, res)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"unreadable payload: {e}")
        res = await solver.solve(ctx)
        if not res.ms:
            res.ms = int((time.time() - t0) * 1000)
        return await _finish(req.type.value, res, req.image_b64)

@router.post("/file", response_model=SolveResponse, summary="Universal solver: file upload (multipart)")
async def solve_file(
    type: str = Form(..., description="Captcha type, e.g. amazon-captcha, slider-captcha (see /v1/capabilities)"),
    file: UploadFile = File(..., description="Main image (captcha, slider background, ...)"),
    file2: Optional[UploadFile] = File(None, description="Second image (slider piece)"),
    instruction: Optional[str] = Form(None, description="Instruction for click-captcha / image grids"),
    sitekey: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
    langs: str = Form("en"),
    timeout: int = Form(90),
):
    """Same universal contract as POST /v1/solve but with raw file upload
    instead of base64. `type` is required."""
    import base64 as _b64
    try:
        raw = await file.read()
        Image.open(io.BytesIO(raw)).convert("RGB")  # validate early
    except Exception:
        raise HTTPException(400, "unreadable image file")
    image_b64 = _b64.b64encode(raw).decode()
    image_b64_2 = None
    if file2 is not None:
        try:
            raw2 = await file2.read()
            Image.open(io.BytesIO(raw2)).convert("RGB")
            image_b64_2 = _b64.b64encode(raw2).decode()
        except Exception:
            raise HTTPException(400, "unreadable second image file")
    try:
        req = SolveRequest(type=type, image_b64=image_b64, image_b64_2=image_b64_2,  # type: ignore
                           instruction=instruction, sitekey=sitekey, url=url,
                           langs=langs, timeout=timeout)
    except Exception:
        raise HTTPException(422, f"unknown type: {type} — see /v1/capabilities")
    return await solve_generic(req)

@router.post("/image", response_model=SolveResponse, summary="Image grid select (3x3, animated included)")
async def solve_image(req: ImageSolveRequest):
    async with SEM:
        solver: ImageSelectSolver = REGISTRY["image-select"]  # type: ignore
        tiles = []
        for t in req.images:
            try:
                if t.image_b64:
                    raw = base64.b64decode(t.image_b64.split(";base64,", 1)[-1] if ";base64," in t.image_b64 else t.image_b64)
                    tiles.append((t.id, raw if req.animated else Image.open(io.BytesIO(raw)).convert("RGB")))
                elif t.image_url:
                    img = await fetch_image(t.image_url)
                    tiles.append((t.id, img))
                else:
                    continue
            except Exception:
                continue
        if not tiles:
            raise HTTPException(400, "no valid image (image_b64 or image_url required)")
        res = await solver.solve_tiles(req.instruction, tiles, animated=req.animated)
        return await _finish("image-select", res)

@router.post("/ocr", response_model=SolveResponse, summary="Local OCR (normal/text/number/ru/zh/amazon/vk/math)")
async def solve_ocr(req: OcrRequest):
    async with SEM:
        kind_map = {"auto": "image-text", "normal": "normal-captcha", "text": "text-captcha",
                    "number": "number-captcha", "russian": "russian-captcha", "chinese": "chinese-captcha",
                    "amazon": "amazon-captcha", "vk": "vk-captcha", "atb": "atb-captcha", "math": "math-captcha"}
        key = kind_map.get(req.kind, "image-text")
        solver = REGISTRY[key]
        try:
            img = b64_to_pil(req.image_b64) if req.image_b64 else await fetch_image(req.image_url or "")
        except Exception as e:
            raise HTTPException(400, f"unreadable image: {e}")
        hit = _recall_ocr(key, img)
        if hit:
            return await _finish(key, hit, req.image_b64)
        res = await solver.solve_pil(img, req.langs)  # type: ignore
        return await _finish(key, res, req.image_b64)

@router.post("/ocr-upload", response_model=SolveResponse, summary="OCR via file upload")
async def solve_ocr_upload(file: UploadFile = File(...), preprocess: bool = Form(True)):
    async with SEM:
        raw = await file.read()
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception:
            raise HTTPException(400, "unreadable image file")
        solver: ImageTextSolver = REGISTRY["image-text"]  # type: ignore
        res = await solver.solve_image(img, preprocess=preprocess)
        return await _finish("image-text", res)

@router.post("/audio", response_model=SolveResponse, summary="Local audio transcription")
async def solve_audio(file: UploadFile = File(...)):
    async with SEM:
        raw = await file.read()
        solver: AudioSolver = REGISTRY["audio"]  # type: ignore
        res = await solver.solve_bytes(raw)
        return await _finish("audio", res)

@router.post("/slider", response_model=SolveResponse, summary="Slider: bg (+piece) -> x + human track")
async def solve_slider(req: SliderRequest):
    async with SEM:
        from ..ai.slider import find_slider_gap_best, human_track
        try:
            bg = b64_to_pil(req.bg_b64) if req.bg_b64 else await fetch_image(req.bg_url or "")
            piece = b64_to_pil(req.piece_b64) if req.piece_b64 else (await fetch_image(req.piece_url) if req.piece_url else None)
        except Exception as e:
            raise HTTPException(400, f"unreadable images: {e}")
        t0 = time.time()
        x, conf, w, via = find_slider_gap_best(bg, piece)
        return await _finish("slider-captcha", SolverResult(ok=conf > 0.15, coords=[x], confidence=conf,
                                  detail={"x": x, "width": w, "via": via, "track": human_track(x)},
                                  ms=int((time.time() - t0) * 1000)), req.bg_b64)

@router.post("/rotate", response_model=SolveResponse, summary="Rotate: image -> angle")
async def solve_rotate(req: RotateRequest):
    async with SEM:
        from ..ai.rotate_click import estimate_rotation_angle
        try:
            img = b64_to_pil(req.image_b64) if req.image_b64 else await fetch_image(req.image_url or "")
        except Exception as e:
            raise HTTPException(400, f"unreadable image: {e}")
        t0 = time.time()
        angle, conf = estimate_rotation_angle(img)
        return await _finish("rotate-captcha", SolverResult(ok=True, coords=[int(angle)], confidence=conf,
                                  detail={"angle": angle}, ms=int((time.time() - t0) * 1000)),
                             req.image_b64)

@router.post("/click", response_model=SolveResponse, summary="Click: image + instruction -> coords 0-1000")
async def solve_click(req: ClickRequest):
    async with SEM:
        from ..ai.rotate_click import click_targets
        from ..ai.instructions import parse_instruction
        try:
            img = b64_to_pil(req.image_b64) if req.image_b64 else await fetch_image(req.image_url or "")
        except Exception as e:
            raise HTTPException(400, f"unreadable image: {e}")
        t0 = time.time()
        parsed = parse_instruction(req.instruction)
        coords, conf, via = click_targets(img, parsed["target_en"])
        return await _finish("click-captcha", SolverResult(ok=bool(coords), coords=[c for p in coords for c in p],
                                  confidence=conf, detail={"points": coords, "via": via, "target": parsed},
                                  ms=int((time.time() - t0) * 1000)), req.image_b64)

@router.post("/pow", response_model=SolveResponse, summary="PoW: Altcha/Friendly/CaptchaFox/Prosopo")
async def solve_pow(req: PowRequest):
    async with SEM:
        key = {"altcha": "altcha", "friendly-captcha": "friendly-captcha",
               "captchafox": "captchafox", "prosopo-procaptcha": "prosopo-procaptcha"}.get(req.type, "altcha")
        solver = REGISTRY[key]
        res = await solver.solve_pow(req.challenge, req.salt, req.maxnumber, req.algorithm)  # type: ignore
        return await _finish(key, res)

@router.post("/math", response_model=SolveResponse, summary="Math: image or text -> answer")
async def solve_math(req: MathRequest):
    async with SEM:
        from ..ai.math_solver import solve_math_text
        t0 = time.time()
        text = req.text or ""
        if not text and (req.image_b64 or req.image_url):
            try:
                img = b64_to_pil(req.image_b64) if req.image_b64 else await fetch_image(req.image_url or "")
            except Exception as e:
                raise HTTPException(400, f"unreadable image: {e}")
            solver = REGISTRY["math-captcha"]
            res = await solver.solve_pil(img)  # type: ignore
            return await _finish("math-captcha", res, req.image_b64)
        ans, conf = solve_math_text(text)
        return await _finish("math-captcha", SolverResult(ok=ans is not None, text=ans, confidence=conf,
                                  detail={"raw": text}, ms=int((time.time() - t0) * 1000)))
