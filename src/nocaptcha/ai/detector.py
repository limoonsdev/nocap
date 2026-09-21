"""Local object detection, light and fast.

Cascade (fast -> accurate):
  1. YOLOv8n (ultralytics, ~6 MB, ~40ms CPU, GPU if available) when installed
  2. CLIP zero-shot (transformers) when installed — best for free-form instructions
  3. OpenCV heuristics (color/shape) — always available, zero AI dependency

Goal: run on a modest CPU box without a GPU.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np
from PIL import Image

@dataclass
class Detection:
    label: str
    score: float
    box: tuple[float, float, float, float] | None = None  # normalized x1,y1,x2,y2

COCO_FR = {
    "bicycle": ["vélo", "velo", "bicyclette", "bike"],
    "car": ["voiture", "auto", "cars"],
    "motorcycle": ["moto", "scooter"],
    "bus": ["bus", "autobus"],
    "truck": ["camion", "truck"],
    "traffic light": ["feu", "feux", "traffic light", "stop light", "feu de circulation", "feux de circulation"],
    "fire hydrant": ["bouche", "hydrant", "borne incendie"],
    "stop sign": ["stop", "panneau stop"],
    "parking meter": ["parcmètre", "horodateur"],
    "bench": ["banc"],
    "dog": ["chien", "dog"],
    "cat": ["chat", "cat"],
    "crosswalk": ["passage piéton", "passage pieton", "crosswalk", "zebra"],
    "bridge": ["pont", "bridge"],
    "chimney": ["cheminée"],
    "boat": ["bateau", "boat"],
    "bicycle": ["bicycle"],
    "stairs": ["escalier", "stairs"],
    "bus stop": ["arrêt de bus"],
    "mountain": ["montagne"],
    "river": ["rivière", "riviere"],
}

class LocalDetector:
    def __init__(self, backend: str = "auto"):
        self.backend = backend
        self._yolo = None
        self._clip = None
        self._clip_proc = None
        self._active = "heuristic"
        try:
            from ..learn.device import torch_device
            self._dev = torch_device()  # cuda > mps > cpu
        except Exception:
            self._dev = "cpu"
        self._init_lazy()

    def _init_lazy(self):
        if self.backend in ("auto", "yolo"):
            try:
                from ultralytics import YOLO
                # shared cache dir first (preloaded by warmup), then CWD (ultralytics default)
                try:
                    from ..config import get_settings
                    cached = get_settings().models_dir / "yolov8n.pt"
                    weight = str(cached) if cached.exists() else "yolov8n.pt"
                except Exception:
                    weight = "yolov8n.pt"
                self._yolo = YOLO(weight)
                self._active = "yolo"
                return
            except Exception:
                pass
        if self.backend in ("auto", "clip"):
            try:
                from transformers import CLIPProcessor, CLIPModel
                import torch
                self._clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
                self._clip_proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
                try:
                    self._clip.to(self._dev)  # GPU si dispo : inference ~5x plus rapide
                except Exception:
                    pass
                self._clip.eval()
                self._active = "clip"
                return
            except Exception:
                pass
        self._active = "heuristic"

    @property
    def active_backend(self) -> str:
        return self._active

    # ---------- API publique ----------
    def contains(self, img: Image.Image, target_en: str, threshold: float = 0.30) -> tuple[bool, float]:
        """Retourne (match, confiance) : l'image contient-elle la cible ?"""
        target_en = target_en.lower().strip()
        if self._active == "yolo" and self._yolo is not None:
            return self._contains_yolo(img, target_en, threshold)
        if self._active == "clip" and self._clip is not None:
            return self._contains_clip(img, target_en, threshold)
        return self._contains_heuristic(img, target_en)

    def batch_contains(self, imgs: list[Image.Image], target_en: str, threshold: float = 0.30) -> list[tuple[bool, float]]:
        return [self.contains(i, target_en, threshold) for i in imgs]

    # ---------- Backends ----------
    def _contains_yolo(self, img: Image.Image, target: str, thr: float):
        try:
            try:
                res = self._yolo.predict(img, verbose=False, conf=0.25, device=self._dev)[0]
            except Exception:
                res = self._yolo.predict(img, verbose=False, conf=0.25)[0]
            names = res.names
            best = 0.0
            for box, cls, conf in zip(res.boxes.xyxy, res.boxes.cls, res.boxes.conf):
                label = str(names[int(cls)]).lower()
                c = float(conf)
                if label == target or target in label or label in target:
                    best = max(best, c)
            return (best >= thr, best)
        except Exception:
            return self._contains_heuristic(img, target)

    def _contains_clip(self, img: Image.Image, target: str, thr: float):
        try:
            import torch
            prompts = [f"a photo of a {target}", "a photo without {target}", f"a street photo with {target}"]
            inputs = self._clip_proc(text=prompts, images=img, return_tensors="pt", padding=True)
            try:
                inputs = {k: v.to(self._dev) if hasattr(v, "to") else v for k, v in inputs.items()}
            except Exception:
                pass
            with torch.no_grad():
                out = self._clip(**inputs)
                probs = out.logits_per_image.softmax(dim=1)[0]
            score = float(probs[0] + probs[2] * 0.5)
            score = min(1.0, score)
            return (score >= thr, score)
        except Exception:
            return self._contains_heuristic(img, target)

    def _contains_heuristic(self, img: Image.Image, target: str) -> tuple[bool, float]:
        """OpenCV fallback: saturated vertical color zones (lights), zebra lines (crosswalks), etc."""
        import cv2
        t = target.lower()
        arr = np.array(img.convert("RGB"))
        hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)

        if "traffic light" in t or "feu" in t:
            # lights = small saturated red/green zones at the top
            red1 = cv2.inRange(hsv, np.array([0, 90, 80]), np.array([10, 255, 255]))
            red2 = cv2.inRange(hsv, np.array([160, 90, 80]), np.array([180, 255, 255]))
            green = cv2.inRange(hsv, np.array([35, 90, 80]), np.array([85, 255, 255]))
            mask = red1 | red2 | green
            ratio = float((mask > 0).mean())
            score = min(1.0, ratio * 25)
            return (score > 0.28, score)
        if "crosswalk" in t or "passage" in t or "zebra" in t:
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            edges = cv2.Canny(bw, 50, 150)
            lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 60, minLineLength=30, maxLineGap=10)
            n = 0 if lines is None else len(lines)
            score = min(1.0, n / 18)
            return (score > 0.30, score)
        if "bus" in t or "car" in t or "truck" in t or "voiture" in t or "camion" in t:
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 60, 160)
            density = float((edges > 0).mean())
            score = min(1.0, density * 6)
            return (score > 0.35, score)
        # default: entropy / texture => neutral 0.5 so OCR or voting decides
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        std = float(gray.std() / 128.0)
        score = max(0.0, min(1.0, std * 0.6))
        return (score > 0.45, score * 0.8)
