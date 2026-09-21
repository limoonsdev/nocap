"""Warmup: on server boot, download + preload ALL optimal resources so the
first request is already at full speed.

Resources:
  onnx/mnist-12, onnx/mobilenetv2-12-int8, onnx/synset (download ~4 MB)
  ddddocr ocr / beta / slide / det (vendored wheel, instantiation = session preload)
  rapidocr (auto-download ~15 MB on first use)
  yolo/yolov8n (optional, auto-download ~6 MB on first use, SOTA offline detection)

Missing OPTIONAL dependencies are SKIPPED (not errors): every solver has a
fallback chain, so the API stays fully functional. Skips are reported with
[\\] plus the one-liner that enables them.

Non-blocking: launched in a background thread at boot (FastAPI lifespan); the API
serves immediately. Live status via GET /v1/models (warmup field) and
`nocaptcha models` / `nocaptcha warmup`.
"""
from __future__ import annotations
import threading
import time

# install hints shown when an optional resource is skipped
HINTS = {
    "yolo/yolov8n": "pip install '.[ai-full]' for YOLOv8 detection",
    "ddddocr": "pip install ddddocr for captcha OCR",
    "rapidocr": "pip install '.[ai-light]' for RapidOCR",
}

_state: dict = {"started": False, "finished": False, "started_at": 0.0,
                "finished_at": 0.0, "items": {}, "errors": []}
_lock = threading.Lock()


def status() -> dict:
    with _lock:
        import copy
        return copy.deepcopy(_state)


def _mark(name: str, ok: bool, ms: int, detail: str = "", skipped: bool = False):
    with _lock:
        _state["items"][name] = {"ok": ok, "ms": ms, "detail": detail, "skipped": skipped}


def _warm_one(name: str, fn):
    t0 = time.time()
    try:
        detail = fn() or ""
        _mark(name, True, int((time.time() - t0) * 1000), str(detail))
    except (ModuleNotFoundError, ImportError) as e:
        # optional dependency absent: skip, never an error
        hint = HINTS.get(name, "")
        detail = f"optional, skipped ({e}). {hint}".strip()
        _mark(name, False, int((time.time() - t0) * 1000), detail[:160], skipped=True)
    except Exception as e:
        with _lock:
            _state["errors"].append(f"{name}: {type(e).__name__}: {e}"[:200])
        _mark(name, False, int((time.time() - t0) * 1000), str(e)[:120])


def warmup_sync() -> dict:
    """Run the full warmup (blocking). Returns the final state."""
    with _lock:
        if _state["started"] and not _state["finished"]:
            pass  # already running elsewhere: still idempotent, run again
        _state.update(started=True, finished=False, started_at=time.time(),
                      finished_at=0.0, items={}, errors=[])
    from .ai.onnx_zoo import ensure

    _warm_one("onnx/mnist-12", lambda: str(ensure("mnist-12") or "cache-missing"))
    _warm_one("onnx/mobilenetv2-12-int8", lambda: str(ensure("mobilenetv2-12-int8") or "cache-missing"))
    _warm_one("onnx/synset", lambda: str(ensure("synset") or "cache-missing"))

    def _dddd():
        from .ai import dddd
        for k in ("ocr", "beta", "slide", "det"):
            dddd._get(k)  # raises ModuleNotFoundError when ddddocr is absent -> skipped
        return "ocr+beta+slide+det preloaded"
    _warm_one("ddddocr", _dddd)

    def _rapid():
        from .ai.ocr import LocalOcr
        o = LocalOcr("rapidocr", "en")
        return f"backend={o.active}"
    _warm_one("rapidocr", _rapid)

    def _yolo():
        # SOTA offline detection for image grids (auto-downloads yolov8n.pt once, ~6 MB)
        from ultralytics import YOLO  # ModuleNotFoundError -> skipped with hint
        from .config import get_settings
        dest = get_settings().models_dir / "yolov8n.pt"
        m = YOLO(str(dest) if dest.exists() else "yolov8n.pt")
        try:
            if not dest.exists():
                import shutil
                src = __import__("pathlib").Path("yolov8n.pt")
                if src.exists():
                    shutil.move(str(src), str(dest))
        except Exception:
            pass
        names = getattr(getattr(m, "model", None), "names", None)
        return f"yolov8n ready ({len(names or [])} classes)"
    _warm_one("yolo/yolov8n", _yolo)

    def _sessions():
        # pre-compile ONNX sessions (first call is slow, then ~ms)
        from .ai import onnx_zoo as z
        from PIL import Image
        z.mnist_digit(Image.new("RGB", (28, 28), "white"))
        z.mobilenet_topk(Image.new("RGB", (64, 64), "white"), k=1)
        return "sessions compiled"
    _warm_one("onnx-sessions", _sessions)

    with _lock:
        _state["finished"] = True
        _state["finished_at"] = time.time()
        import copy
        final = copy.deepcopy(_state)
    try:
        from .log import ok, err, info
        items = final["items"].values()
        n_ok = sum(1 for v in items if v["ok"])
        n_skip = sum(1 for v in final["items"].values() if v.get("skipped"))
        n = len(final["items"])
        dt = final["finished_at"] - final["started_at"]
        if n_ok + n_skip == n:
            if n_skip:
                info(f"warmup finished: {n_ok}/{n} ready, {n_skip} skipped (optional) in {dt:.1f}s")
            else:
                ok(f"warmup finished: {n_ok}/{n} resources ready in {dt:.1f}s")
            for k, v in final["items"].items():
                if v.get("skipped"):
                    info(f"skipped (optional): {k} — {v.get('detail', '')}")
        else:
            err(f"warmup finished with gaps: {n_ok}/{n} ready in {dt:.1f}s (fallbacks active)")
            for e in final["errors"]:
                err(e)
    except Exception:
        pass
    return final


def warmup_background():
    """Launch warmup in a background thread (server lifespan). Idempotent."""
    with _lock:
        if _state["started"]:
            return False
        _state["started"] = True
    th = threading.Thread(target=warmup_sync, name="nocaptcha-warmup", daemon=True)
    th.start()
    return True
