"""Auto-capture + auto-entrainement : chaque captcha resolu ameliore le suivant.

1. CAPTURE : chaque solve OK sauvegarde (image b64, type, solution, confiance, ms)
   dans ./models/captures/<type>/ + manifest.jsonl
2. RECALL : classifieur GPU/CPU entraine (learn/trainer.py, `via=gpu-classifier`),
   puis hash perceptuel + template-match (`via=hash-hit/template-hit`, <5ms).
3. AUTO-TRAIN : `nocaptcha train [--type X --epochs N]` (GPU auto : CUDA > MPS > CPU,
   AMP fp16, batch) + `POST /v1/dataset/train`. Sans GPU/torch : fallback banque CPU.

Voir learn/device.py (detection GPU) et learn/trainer.py (CNN leger + ONNX).
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import time
from pathlib import Path
from PIL import Image

from ..config import get_settings

def _dir() -> Path:
    s = get_settings()
    d = s.learn_dir if str(s.learn_dir) else (s.models_dir / "captures")
    Path(d).mkdir(parents=True, exist_ok=True)
    return Path(d)

def _ahash(img: Image.Image) -> str:
    """Hash perceptuel 8x8 (robuste au bruit leger)."""
    g = img.convert("L").resize((8, 8), Image.BILINEAR)
    import numpy as _np
    px = _np.asarray(g, dtype=_np.float32).ravel().tolist()
    avg = sum(px) / len(px)
    bits = "".join("1" if p > avg else "0" for p in px)
    return f"{int(bits, 2):016x}"

def save_capture(type_: str, image_b64: str | None, solution: dict, ms: int = 0, conf: float = 0.0):
    """Sauvegarde non-bloquante (best-effort). Retourne le chemin ou None."""
    try:
        s = get_settings()
        if not s.learn_enabled:
            return None
        if not image_b64 or not solution:
            return None
        raw = base64.b64decode(image_b64.split(";base64,", 1)[-1] if ";base64," in image_b64 else image_b64)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        h = _ahash(img)
        folder = _dir() / type_
        folder.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        name = f"{ts}_{h}.png"
        (folder / name).write_bytes(raw)
        entry = {"ts": ts, "type": type_, "file": name, "hash": h,
                 "solution": solution, "ms": ms, "conf": conf}
        with open(_dir() / "manifest.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return str(folder / name)
    except Exception:
        return None

def recall(type_: str, img: Image.Image, threshold: float = 0.92) -> dict | None:
    """Cherche un quasi-doublon dans la banque. Retourne la solution memorisee ou None."""
    try:
        folder = _dir() / type_
        if not folder.exists():
            return None
        import cv2
        import numpy as np
        target = np.array(img.convert("RGB"))
        th, tw = target.shape[:2]
        best: dict | None = None
        best_score = 0.0
        # compare au hash d'abord (rapide), puis template-match sur candidats
        want = _ahash(img)
        cands = sorted(folder.glob("*.png"))[-200:]  # fenetre recente
        for p in cands:
            try:
                if p.stem.endswith(want):
                    # hit exact de hash -> lecture manifest
                    sol = _solution_for(p.name, type_)
                    if sol:
                        return {"solution": sol, "score": 1.0, "via": "hash-hit"}
                cand = np.array(Image.open(p).convert("RGB"))
                if cand.shape[0] > th or cand.shape[1] > tw:
                    continue
                res = cv2.matchTemplate(
                    cv2.cvtColor(target, cv2.COLOR_RGB2GRAY),
                    cv2.cvtColor(cand, cv2.COLOR_RGB2GRAY), cv2.TM_CCOEFF_NORMED)
                _, score, _, _ = cv2.minMaxLoc(res)
                if score > best_score:
                    best_score = float(score)
                    best = {"file": p.name}
            except Exception:
                continue
        if best and best_score >= threshold:
            sol = _solution_for(best["file"], type_)
            if sol:
                return {"solution": sol, "score": best_score, "via": "template-hit"}
        return None
    except Exception:
        return None

def _solution_for(fname: str, type_: str) -> dict | None:
    try:
        mp = _dir() / "manifest.jsonl"
        if not mp.exists():
            return None
        out = None
        for line in mp.read_text(encoding="utf-8").splitlines()[-5000:]:
            try:
                e = json.loads(line)
                if e.get("file") == fname and e.get("type") == type_:
                    out = e.get("solution")
            except Exception:
                continue
        return out
    except Exception:
        return None

def train_summary() -> dict:
    """Consolide : dedup par hash, compte par type, taille. Utilise par `nocaptcha train`."""
    d = _dir()
    mp = d / "manifest.jsonl"
    total = 0
    per: dict[str, int] = {}
    hashes: set[str] = set()
    dups = 0
    if mp.exists():
        for line in mp.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
                total += 1
                per[e.get("type", "?")] = per.get(e.get("type", "?"), 0) + 1
                h = e.get("hash", "")
                if h in hashes:
                    dups += 1
                hashes.add(h)
            except Exception:
                continue
    # ecrit un resume pour le lab
    summary = {"captures": total, "by_type": per, "unique_hashes": len(hashes),
               "duplicates": dups, "dir": str(d)}
    try:
        (d / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    except Exception:
        pass
    return summary
