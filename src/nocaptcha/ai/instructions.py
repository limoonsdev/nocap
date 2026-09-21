"""reCAPTCHA / hCaptcha instruction parsing (FR + EN), no LLM.

Examples:
  "Select all images with traffic lights" -> traffic light
  "Select all images with crosswalks" -> crosswalk
  "Click each image containing a bus" -> bus
Returns (target_en, target_fr, challenge kind).
"""
from __future__ import annotations
import re
import unicodedata
from .detector import COCO_FR

CANON = {
    "traffic light": ["traffic light", "feu", "feux"],
    "crosswalk": ["crosswalk", "passage pieton", "zebra"],
    "bus": ["bus"],
    "car": ["car", "voiture", "auto"],
    "bicycle": ["bicycle", "velo", "bike"],
    "motorcycle": ["motorcycle", "moto"],
    "truck": ["truck", "camion"],
    "fire hydrant": ["fire hydrant", "hydrant", "bouche"],
    "stop sign": ["stop sign", "panneau stop"],
    "boat": ["boat", "bateau"],
    "bridge": ["bridge", "pont"],
    "chimney": ["chimney", "cheminee"],
    "stairs": ["stairs", "escalier"],
    "dog": ["dog", "chien"],
    "cat": ["cat", "chat"],
}

def _norm(s: str) -> str:
    s = s.lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()

def parse_instruction(text: str) -> dict:
    n = _norm(text)
    for en, kws in CANON.items():
        for k in kws:
            if _norm(k) in n:
                fr = COCO_FR.get(en, [en])[0] if en in COCO_FR else en
                # dynamic / select-all / single ?
                kind = "select-all"
                if any(w in n for w in ["clic", "click each", "une seule", "single"]):
                    kind = "single"
                return {"target_en": en, "target_fr": fr, "kind": kind, "raw": text}
    # generic fallback: extract the trailing noun group
    m = re.search(r"(avec des|with|containing|contenant)\s+([a-zà-ÿ ]+)", n)
    guess = m.group(2).strip() if m else text.strip()
    return {"target_en": guess, "target_fr": guess, "kind": "select-all", "raw": text, "uncertain": True}
