"""Metriques de performance : vitesse moyenne de resolution en secondes.

- Compte chaque solve (ok/ko, ms) par type + global
- Moyenne, p50/p95, taux de succes, dernier solve
- Persiste en JSON (models/metrics.json), thread-safe asyncio
- Expose via /v1/stats et /v1/stats/reset
Aucun rate-limit : simple compteur atomique, cout ~microsecondes.
"""
from __future__ import annotations
import asyncio
import json
import time
from pathlib import Path
from .config import get_settings

_lock = asyncio.Lock()
_cache: dict | None = None

def _path() -> Path:
    s = get_settings()
    s.models_dir.mkdir(parents=True, exist_ok=True)
    return s.models_dir / "metrics.json"

def _blank() -> dict:
    return {"started_at": time.time(), "total": 0, "ok": 0, "ko": 0,
            "total_ms": 0, "by_type": {}}

async def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    p = _path()
    if p.exists():
        try:
            _cache = json.loads(p.read_text(encoding="utf-8"))
            _cache.setdefault("by_type", {})
            return _cache
        except Exception:
            pass
    _cache = _blank()
    return _cache

def _save_sync(data: dict):
    try:
        _path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass

async def record(type_: str, ok: bool, ms: int):
    """Enregistre un solve. ms = temps total (IA + navigateur)."""
    async with _lock:
        d = await _load()
        d["total"] += 1
        d["ok" if ok else "ko"] += 1
        d["total_ms"] += max(0, ms)
        b = d["by_type"].setdefault(type_, {"n": 0, "ok": 0, "ms": [], "total_ms": 0})
        b["n"] += 1
        b["ok"] += 1 if ok else 0
        b["total_ms"] += max(0, ms)
        b["ms"].append(max(0, ms))
        if len(b["ms"]) > 500:  # fenetre glissante (perf + vie privee)
            b["ms"] = b["ms"][-500:]
        b["avg_s"] = round(b["total_ms"] / max(1, b["n"]) / 1000, 3)
        b["success"] = round(b["ok"] / max(1, b["n"]), 3)
        try:
            srt = sorted(b["ms"])
            b["p50_s"] = round(srt[len(srt)//2] / 1000, 3)
            b["p95_s"] = round(srt[int(len(srt)*0.95)] / 1000, 3)
        except Exception:
            pass
        d["avg_s"] = round(d["total_ms"] / max(1, d["total"]) / 1000, 3)
        d["success"] = round(d["ok"] / max(1, d["total"]), 3)
        _save_sync(d)

async def snapshot() -> dict:
    async with _lock:
        d = await _load()
        return json.loads(json.dumps(d))

async def reset():
    global _cache
    async with _lock:
        _cache = _blank()
        _save_sync(_cache)
        return _cache
