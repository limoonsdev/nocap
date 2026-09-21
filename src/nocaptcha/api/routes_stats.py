"""Routes stats / dataset / device / models: average speed, GPU auto-train, 0 rate-limit."""
from __future__ import annotations
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel, Field
from .. import metrics as M
from ..learn import train_summary
from ..learn.device import device_summary
from ..models import TrainRequest
from ..config import get_settings

_to_thread = asyncio.to_thread

router = APIRouter(tags=["stats"])

@router.get("/device", summary="Detected device: GPU when available, else CPU")
async def device():
    return {"ok": True, **device_summary(get_settings().device)}

@router.get("/stats", summary="Average speed (s), p50/p95, success rate per type")
async def stats():
    d = await M.snapshot()
    return {"ok": True, **d}

@router.post("/stats/reset", summary="Reset counters")
async def stats_reset():
    d = await M.reset()
    return {"ok": True, **d}

@router.get("/dataset/summary", summary="Auto-learn state (captures)")
async def dataset_summary():
    return {"ok": True, **train_summary(), **{"device": device_summary()["device"]}}

@router.post("/dataset/train", summary="Train on GPU when available: bank + classifier (AMP, batch)")
async def dataset_train(req: TrainRequest | None = None):
    s = train_summary()
    if not req or not req.type:
        return {"ok": True, **s, "trained": "bank", "device": device_summary()["device"]}
    from ..learn.trainer import train_classifier
    rep = train_classifier(req.type, epochs=req.epochs, batch=req.batch,
                           lr=req.lr, device=req.device, amp=req.amp)
    return {"ok": bool(rep.get("ok")), **s, "report": rep, "trained": "classifier" if rep.get("ok") else False}

@router.get("/limits", summary="0 rate-limit proof")
async def limits():
    s = get_settings()
    return {"ok": True, "api_rate_limit": s.api_rate_limit,
            "max_concurrent_solves": s.max_concurrent_solves,
            "pool_max_contexts": s.pool_max_contexts,
            "note": "No artificial limit: wide semaphore + reused Playwright pool."}

class ModelsDownload(BaseModel):
    name: str | None = Field(None, description="Model name (empty = all)")

@router.get("/models", summary="Models + warmup: full resource status")
async def models_status():
    from ..ai.onnx_zoo import status as zoo_status
    from .. import resources
    return {"ok": True, "models": zoo_status(), "warmup": resources.status()}

@router.post("/models/download", summary="Download + preload everything (ONNX, ddddocr, rapidocr)")
async def models_download(req: ModelsDownload | None = None):
    from ..ai.onnx_zoo import ensure, status, REGISTRY
    from .. import resources
    names = [req.name] if req and req.name else list(REGISTRY.keys())
    got = {}
    for n in names:
        if n not in REGISTRY:
            got[n] = {"ok": False, "error": "unknown"}
            continue
        p = await _to_thread(ensure, n)
        got[n] = {"ok": p is not None, "path": str(p) if p else None}
    # also preload heavy singletons (ddddocr sessions, rapidocr)
    st = await _to_thread(resources.warmup_sync)
    return {"ok": all(v.get("ok") for v in got.values()), "done": got,
            "models": (await models_status())["models"], "warmup": st}
