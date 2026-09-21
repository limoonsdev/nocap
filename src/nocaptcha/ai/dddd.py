"""ddddocr — LA reference captcha (sml2h3, GitHub) : modeles ONNX vended dans le wheel.

- classification : texte captcha FR/EN/chiffres (+chinois), modele `common_old`
  (13 Mo, rapide) + `beta` `common` (51 Mo, complexe). Sans confiance calibree :
  on renvoie conf heuristique + via honnete.
- slide_match : gap slider (piece + bg) — utilise en ENSEMBLE avec notre
  template-match OpenCV (on garde le meilleur score).
- detection : boites d'objets (det=True) — expose pour click-captcha futur.
- GPU : use_gpu=True seulement si torch CUDA + onnxruntime-gpu (sinon crash) ;
  on reste CPU par defaut (rapide : ~30ms/OCR).

Tout est lazy + garde : sans ddddocr installe, chaque fonction renvoie None/0.
Modeles precharges au demarrage serveur via resources.warmup().
"""
from __future__ import annotations
import io
from PIL import Image

_singletons: dict[str, object] = {}


def available() -> bool:
    try:
        import ddddocr  # noqa: F401
        return True
    except Exception:
        return False


def _use_gpu() -> bool:
    try:
        from ..learn.device import torch_device
        if torch_device() != "cuda":
            return False
        import onnxruntime as ort  # noqa: F401
        return "CUDAExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


def _get(kind: str):
    """Singletons : 'ocr' | 'beta' | 'slide' | 'det'. Leve si indisponible."""
    if kind in _singletons:
        return _singletons[kind]
    import ddddocr
    kw = {"show_ad": False, "use_gpu": _use_gpu()}
    if kind == "ocr":
        obj = ddddocr.DdddOcr(ocr=True, det=False, **kw)
    elif kind == "beta":
        obj = ddddocr.DdddOcr(ocr=True, det=False, beta=True, **kw)
    elif kind == "slide":
        obj = ddddocr.DdddOcr(det=False, ocr=False, **kw)
    elif kind == "det":
        obj = ddddocr.DdddOcr(det=True, **kw)
    else:
        raise ValueError(kind)
    _singletons[kind] = obj
    return obj


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def classify(img: Image.Image, beta: bool = False) -> tuple[str, float, str]:
    """(texte, conf_heuristique, via). Texte '' si echec. Conf = 0.8/0.7 non-calibree."""
    try:
        obj = _get("beta" if beta else "ocr")
        txt = obj.classification(_png_bytes(img)) or ""
        txt = str(txt).strip()
        if not txt:
            return "", 0.0, "ddddocr"
        return txt, (0.7 if beta else 0.8), ("ddddocr-beta" if beta else "ddddocr")
    except Exception:
        return "", 0.0, "ddddocr"


def classify_best(img: Image.Image) -> tuple[str, float, str]:
    """Essaie standard puis beta, garde le plus long non-vide (captchas = longs)."""
    t1, c1, v1 = classify(img, beta=False)
    try:
        t2, c2, v2 = classify(img, beta=True)
    except Exception:
        return t1, c1, v1
    # heuristique : le vrai captcha est rarement 1 caractere CJK isole
    if t2 and (len(t2) > len(t1) or not t1):
        return t2, c2, v2
    return t1, c1, v1


def slide_x(piece: Image.Image, bg: Image.Image) -> tuple[int | None, float]:
    """Position x du gap via ddddocr slide_match. (None, 0.0) si echec."""
    try:
        obj = _get("slide")
        res = obj.slide_match(_png_bytes(piece), _png_bytes(bg), simple_target=True)
        if isinstance(res, dict):
            x = res.get("target_x", (res.get("target") or [None])[0])
            c = float(res.get("confidence", 0.8))
            if x is not None:
                return int(x), max(0.0, min(1.0, c))
        return None, 0.0
    except Exception:
        return None, 0.0


def detect_boxes(img: Image.Image) -> list[list[int]]:
    """Boites d'objets [x1,y1,x2,y2]. [] si indisponible."""
    try:
        obj = _get("det")
        out = obj.detection(_png_bytes(img)) or []
        return [[int(v) for v in b] for b in out if len(b) >= 4]
    except Exception:
        return []
