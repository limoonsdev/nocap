"""Zoo de petits modeles ONNX — rapides, precis, 100% locaux.

Modeles (URLs verifiees, telecharges une fois dans ./models/onnx/) :
  mnist-12 (26 Ko)              — chiffres manuscrits 0-9 (number-captcha)
  mobilenetv2-12-int8 (3.6 Mo)  — 1000 classes ImageNet quantifie (tuiles image-select)
  synset.txt                    — labels ImageNet
  rapidocr (pip)                — detection + reconnaissance texte multilingue (via rapidocr_onnxruntime)

Sans reseau / sans onnxruntime : tout echoue proprement (None/False) et les
solvers retombent sur heuristiques + OCR classique. Jamais de crash.
"""
from __future__ import annotations
import time
import urllib.request
from pathlib import Path
from PIL import Image

from ..config import get_settings

BASE = "https://github.com/onnx/models/raw/main/validated/vision/classification"

REGISTRY: dict[str, dict] = {
    "mnist-12": {
        "url": f"{BASE}/mnist/model/mnist-12.onnx",
        "size": 26143, "desc": "Chiffres 0-9 (28x28) — number-captcha",
    },
    "mobilenetv2-12-int8": {
        "url": f"{BASE}/mobilenet/model/mobilenetv2-12-int8.onnx",
        "size": 3655033, "desc": "1000 classes ImageNet quantifie — tuiles image-select",
    },
    "synset": {
        "url": f"{BASE}/synset.txt",
        "size": 30000, "desc": "Labels ImageNet (1000 lignes)",
    },
}

_sessions: dict[str, object] = {}
_synset: list[str] | None = None


def onnx_dir() -> Path:
    d = get_settings().models_dir / "onnx"
    d.mkdir(parents=True, exist_ok=True)
    return d


def model_path(name: str) -> Path:
    ext = ".txt" if name == "synset" else ".onnx"
    return onnx_dir() / f"{name}{ext}"


def is_cached(name: str) -> bool:
    p = model_path(name)
    if not p.exists():
        return False
    want = REGISTRY.get(name, {}).get("size", 0)
    try:
        # taille exacte pour .onnx, approximative pour synset
        return p.stat().st_size == want if name != "synset" else p.stat().st_size > 10000
    except Exception:
        return False


def ensure(name: str, timeout: int = 120) -> Path | None:
    """Telecharge le modele si absent. Retourne le chemin ou None (offline/erreur)."""
    if name not in REGISTRY:
        return None
    p = model_path(name)
    if is_cached(name):
        return p
    try:
        tmp = p.with_suffix(p.suffix + ".tmp")
        req = urllib.request.Request(REGISTRY[name]["url"], headers={"User-Agent": "nocaptcha"})
        with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
            f.write(r.read())
        tmp.replace(p)
        return p if is_cached(name) else None
    except Exception:
        try:
            tmp.unlink(missing_ok=True)  # type: ignore
        except Exception:
            pass
        return None


def status() -> dict:
    out = {}
    for name, meta in REGISTRY.items():
        p = model_path(name)
        out[name] = {"cached": is_cached(name), "size": meta["size"],
                     "desc": meta["desc"], "path": str(p)}
    # rapidocr (package pip, modeles auto-telecharges au 1er usage)
    try:
        import rapidocr_onnxruntime  # noqa: F401
        out["rapidocr"] = {"cached": True, "size": 0,
                           "desc": "OCR det/rec/cls via pip (auto-download)",
                           "path": "rapidocr_onnxruntime"}
    except Exception:
        out["rapidocr"] = {"cached": False, "size": 0,
                           "desc": "OCR pip : extra ai-light requis", "path": ""}
    # ddddocr (GitHub sml2h3, modeles vended dans le wheel : ocr 13 Mo, beta 51 Mo, det 19 Mo)
    try:
        import ddddocr as _d
        import os as _os
        _dir = _os.path.dirname(_d.__file__)
        _total = sum(_os.path.getsize(_os.path.join(_dir, f)) for f in _os.listdir(_dir) if f.endswith(".onnx"))
        try:
            from .dddd import _singletons
            _loaded = sum(1 for k in ("ocr", "beta", "slide", "det") if k in _singletons)
        except Exception:
            _loaded = 0
        out["ddddocr"] = {"cached": True, "size": _total,
                          "desc": f"OCR captcha sml2h3 (ocr+beta+slide+det, {_loaded}/4 precharges)",
                          "path": _dir}
    except Exception:
        out["ddddocr"] = {"cached": False, "size": 0,
                          "desc": "OCR captcha : pip install ddddocr", "path": ""}
    return out


def _session(name: str):
    """Session onnxruntime cachee (providers GPU si dispo). None si indisponible."""
    if name in _sessions:
        return _sessions[name]
    try:
        import onnxruntime as ort
        from ..learn.device import onnx_providers
        p = model_path(name)
        if not is_cached(name):
            return None
        sess = ort.InferenceSession(str(p), providers=onnx_providers())
        _sessions[name] = sess
        return sess
    except Exception:
        return None


def synset() -> list[str]:
    global _synset
    if _synset is not None:
        return _synset
    try:
        p = model_path("synset")
        if not is_cached("synset") and ensure("synset") is None:
            return []
        _synset = p.read_text(encoding="utf-8").splitlines()
        return _synset
    except Exception:
        return []


# ---------- MNIST : chiffres ----------
def mnist_digit(img: Image.Image) -> tuple[int | None, float]:
    """Un chiffre 28x28 centre -> (digit, conf). None si modele/session absent."""
    sess = _session("mnist-12")
    if sess is None:
        return None, 0.0
    try:
        import numpy as np
        g = img.convert("L").resize((28, 28), Image.BILINEAR)
        arr = (255 - np.asarray(g, dtype=np.float32)) / 255.0  # fond noir, trait blanc
        arr = arr.reshape(1, 1, 28, 28)
        out = sess.run(None, {sess.get_inputs()[0].name: arr})[0][0]
        e = np.exp(out - out.max())
        prob = e / e.sum()
        return int(prob.argmax()), float(prob.max())
    except Exception:
        return None, 0.0


def mnist_read(img: Image.Image, max_chars: int = 8) -> tuple[str | None, float]:
    """Captcha numerique multi-chiffres : segmentation par contours -> MNIST.

    Retourne (texte, conf_moyenne) ou (None, 0.0) si modele absent / indechiffrable.
    """
    if _session("mnist-12") is None:
        return None, 0.0
    try:
        import cv2
        import numpy as np
        arr = np.array(img.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        h, w = gray.shape
        boxes = []
        for c in cnts:
            x, y, cw, ch = cv2.boundingRect(c)
            if ch < h * 0.35 or cw < 3 or (x == 0 and cw > w * 0.9):
                continue  # bruit / bordure
            boxes.append((x, y, cw, ch))
        boxes = sorted(boxes, key=lambda b: b[0])[:max_chars]
        if not boxes:
            return None, 0.0
        out, confs = "", []
        for x, y, cw, ch in boxes:
            pad = max(2, int(ch * 0.12))
            x0, y0 = max(0, x - pad), max(0, y - pad)
            x1, y1 = min(w, x + cw + pad), min(h, y + ch + pad)
            cell = Image.fromarray(gray[y0:y1, x0:x1])
            # carre 28x28 en preservant le ratio
            side = max(cell.size)
            sq = Image.new("L", (side, side), 255)
            sq.paste(cell, ((side - cell.width) // 2, (side - cell.height) // 2))
            d, c = mnist_digit(sq)
            if d is None:
                return None, 0.0
            out += str(d)
            confs.append(c)
        if not out:
            return None, 0.0
        return out, float(sum(confs) / len(confs))
    except Exception:
        return None, 0.0


# ---------- MobileNet : tuiles image-select ----------
_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)

# Mots-cles captcha -> mots-cles synset (recherche substring, insensible casse)
TARGET_KEYWORDS: dict[str, list[str]] = {
    "traffic light": ["traffic light", "stoplight", "traffic signal"],
    "bus": ["school bus", "trolleybus", "minibus", "bus"],
    "car": ["sports car", "racer", "convertible", "jeep", "limousine", "cab", "model t"],
    "bicycle": ["bicycle-built", "tandem", "unicycle", "tricycle"],
    "motorcycle": ["motor scooter", "scooter", "moped"],
    "truck": ["pickup", "tow truck", "trailer truck", "fire engine", "garbage truck"],
    "boat": ["speedboat", "lifeboat", "fireboat", "canoe", "yacht", "sailboat"],
    "bridge": ["steel arch bridge", "suspension bridge", "viaduct"],
    "fire hydrant": ["fire engine"],  # pas de classe hydrant : approx pompier
    "stop sign": ["street sign"],
    "parking meter": ["parking meter"],
    "crosswalk": ["street sign"],  # approx : signalisation rue
    "cat": ["tabby", "tiger cat", "persian cat", "siamese cat", "egyptian cat"],
    "dog": ["labrador", "beagle", "bulldog", "poodle", "retriever", "shepherd", "terrier", "husky"],
    "chimney": ["chimney"],
    "stairs": ["stair"],
}


def mobilenet_topk(img: Image.Image, k: int = 5) -> list[tuple[str, float]]:
    """Top-k ImageNet (label, prob). [] si modele absent."""
    sess = _session("mobilenetv2-12-int8")
    labels = synset()
    if sess is None or not labels:
        return []
    try:
        import numpy as np
        r = img.convert("RGB").resize((224, 224), Image.BILINEAR)
        arr = np.asarray(r, dtype=np.float32) / 255.0
        mean = np.array(_IMAGENET_MEAN, dtype=np.float32).reshape(1, 1, 3)
        std = np.array(_IMAGENET_STD, dtype=np.float32).reshape(1, 1, 3)
        arr = ((arr - mean) / std).transpose(2, 0, 1)[None]
        out = sess.run(None, {sess.get_inputs()[0].name: arr})[0][0]
        e = np.exp(out - out.max())
        prob = e / e.sum()
        idx = prob.argsort()[::-1][:k]
        return [(labels[i] if i < len(labels) else f"cls{i}", float(prob[i])) for i in idx]
    except Exception:
        return []


def mobilenet_contains(img: Image.Image, target_en: str, threshold: float = 0.08) -> tuple[bool, float]:
    """La tuile contient-elle la cible (via MobileNet) ? (match, meilleure prob)."""
    keys = TARGET_KEYWORDS.get(target_en.lower().strip())
    if keys is None:
        # fallback : mots du target cherches dans les labels
        keys = [target_en.lower().strip()]
    top = mobilenet_topk(img, k=8)
    if not top:
        return False, 0.0
    best = 0.0
    for label, p in top:
        ll = label.lower()
        for kw in keys:
            if kw in ll or ll in kw:
                best = max(best, p)
    # bonus position : le top-1 compte double s'il matche
    return (best >= threshold, best)
