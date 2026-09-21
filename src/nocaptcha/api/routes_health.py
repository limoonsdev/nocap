"""Routes /v1/health + /v1/capabilities."""
from __future__ import annotations
from fastapi import APIRouter
from ..models import Capability
from ..solvers import REGISTRY
from ..config import get_settings
from .. import __version__

router = APIRouter(tags=["system"])

@router.get("/health", summary="Service health")
async def health():
    s = get_settings()
    return {"ok": True, "service": "nocaptcha", "version": __version__, "port": s.port}

@router.get("/capabilities", response_model=list[Capability], summary="Supported captcha types")
async def capabilities():
    return [v.capabilities() for v in REGISTRY.values()]
