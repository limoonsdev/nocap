"""OCR local multi-moteur : ddddocr (captcha-specialise, GitHub sml2h3) -> RapidOCR -> EasyOCR -> Tesseract.

Ordre adapte au kind : les captchas courts/bruites (number/normal/amazon/...) vont
d'abord sur ddddocr (entraine sur captchas), le texte courant sur RapidOCR/EasyOCR.
GPU : EasyOCR gpu=True si CUDA/MPS ; ddddocr use_gpu si onnxruntime-gpu present.
"""
from __future__ import annotations
from PIL import Image
from ..utils.image import preprocess_for_ocr

CAPTCHA_FIRST = {"number", "normal", "amazon", "vk", "atb", "math"}

class LocalOcr:
    def __init__(self, backend: str = "auto", langs: str = "fr,en", kind: str = "auto"):
        self.backend = backend
        self.langs = [l.strip() for l in langs.split(",") if l.strip()]
        self.kind = (kind or "auto").lower()
        self._rapid = None
        self._easy = None
        self._active = "none"
        self._init()

    def _order(self) -> list[str]:
        if self.backend != "auto":
            return [self.backend]
        if self.kind in CAPTCHA_FIRST:
            return ["ddddocr", "ddddocr-beta", "rapidocr", "easyocr", "tesseract"]
        return ["rapidocr", "easyocr", "ddddocr", "ddddocr-beta", "tesseract"]

    def _init(self):
        for b in self._order():
            try:
                if b == "ddddocr":
                    from .dddd import available
                    if available():
                        self._active = "ddddocr"
                        return
                    continue
                if b == "ddddocr-beta":
                    from .dddd import available
                    if available():
                        self._active = "ddddocr-beta"
                        return
                    continue
                if b == "rapidocr":
                    from rapidocr_onnxruntime import RapidOCR
                    self._rapid = RapidOCR()
                    self._active = "rapidocr"
                    return
                if b == "easyocr":
                    import easyocr
                    from ..learn.device import torch_device
                    _emap = {"zh": "ch_sim", "cn": "ch_sim", "ru": "ru", "fr": "fr", "en": "en"}
                    codes = [_emap.get(l.lower().split("-")[0], l.split("-")[0]) for l in self.langs]
                    use_gpu = torch_device() in ("cuda", "mps")  # GPU si dispo : ~3-5x plus rapide
                    self._easy = easyocr.Reader(codes, gpu=use_gpu)
                    self._gpu = use_gpu
                    self._active = "easyocr"
                    return
                if b == "tesseract":
                    import pytesseract  # noqa: F401 — binaire tesseract requis
                    self._active = "tesseract"
                    return
            except Exception:
                continue
        # last resort tesseract even if the pytesseract import is missing
        try:
            import shutil
            if shutil.which("tesseract"):
                self._active = "tesseract"
            else:
                self._active = "none"
        except Exception:
            self._active = "none"

    @property
    def active(self): return self._active

    def read(self, img: Image.Image, preprocess: bool = True) -> tuple[str, float]:
        work = preprocess_for_ocr(img) if preprocess else img
        if self._active in ("ddddocr", "ddddocr-beta"):
            try:
                from .dddd import classify
                txt, conf, via = classify(work, beta=(self._active == "ddddocr-beta"))
                if txt:
                    self._via = via
                    return txt, conf
            except Exception:
                pass
        if self._active == "rapidocr":
            try:
                import numpy as np
                res, _ = self._rapid(np.array(work))
                if not res: return "", 0.0
                txt = " ".join([r[1] for r in res])
                conf = float(sum(r[2] for r in res) / len(res))
                return txt.strip(), conf
            except Exception: pass
        if self._active == "easyocr":
            try:
                import numpy as np
                out = self._easy.readtext(np.array(work))
                if not out: return "", 0.0
                txt = " ".join([o[1] for o in out])
                conf = float(sum(o[2] for o in out) / len(out))
                return txt.strip(), conf
            except Exception: pass
        if self._active == "tesseract":
            try:
                import pytesseract
                _map = {"fr": "fra", "en": "eng", "ru": "rus", "zh": "chi_sim", "cn": "chi_sim"}
                lang = "+".join([_map.get(l.lower().split("-")[0], l) for l in self.langs])
                cfg = "--oem 1 --psm 6"
                txt = pytesseract.image_to_string(work, lang=lang, config=cfg)
                data = pytesseract.image_to_data(work, lang=lang, config=cfg, output_type=pytesseract.Output.DATAFRAME)
                try:
                    conf = float(data["conf"].replace(-1, float("nan")).dropna().mean() / 100.0)
                except Exception:
                    conf = 0.6 if txt.strip() else 0.0
                return txt.strip(), max(0.0, min(1.0, conf))
            except Exception as e:
                return "", 0.0
        return "", 0.0
