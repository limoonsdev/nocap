"""Detection centrale du device : GPU quand dispo, CPU sinon.

Priorite : CUDA > MPS (Apple) > CPU. Aucune dependance dure :
torch / onnxruntime sont optionnels, tout est garde en try/except.

Utilise par :
- learn/trainer.py (entrainement CNN, AMP sur CUDA)
- ai/ocr.py (EasyOCR gpu flag, RapidOCR providers)
- ai/detector.py (YOLO device, CLIP .to(device))
"""
from __future__ import annotations
from functools import lru_cache


def torch_device(prefer: str = "auto") -> str:
    """Retourne 'cuda' | 'mps' | 'cpu'. prefer peut forcer ('cuda','mps','cpu','auto')."""
    prefer = (prefer or "auto").lower()
    if prefer in ("cuda", "mps", "cpu"):
        if prefer == "cpu":
            return "cpu"
        try:
            import torch
            if prefer == "cuda" and torch.cuda.is_available():
                return "cuda"
            if prefer == "mps" and getattr(torch.backends, "mps", None) is not None \
                    and torch.backends.mps.is_available():
                return "mps"
        except Exception:
            pass
        return "cpu"
    # auto
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def cuda_info() -> dict:
    """Details GPU (vide si absent). Jamais d'exception."""
    out: dict = {"device": torch_device(), "torch": None, "cuda_available": False,
                 "gpu_count": 0, "gpu_names": [], "amp": False}
    try:
        import torch
        out["torch"] = torch.__version__
        out["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            out["gpu_count"] = int(torch.cuda.device_count())
            try:
                out["gpu_names"] = [torch.cuda.get_device_name(i) for i in range(out["gpu_count"])]
            except Exception:
                pass
            out["amp"] = True  # GradScaler + autocast dispos sur CUDA
    except Exception:
        pass
    return out


def onnx_providers(prefer_gpu: bool = True) -> list[str]:
    """Providers ONNX par ordre de preference (GPU d'abord si dispo)."""
    try:
        import onnxruntime as ort
        avail = set(ort.get_available_providers())
        ordered = []
        if prefer_gpu:
            for p in ("CUDAExecutionProvider", "CoreMLExecutionProvider",
                      "DirectMLExecutionProvider", "MIGraphXExecutionProvider"):
                if p in avail:
                    ordered.append(p)
        ordered.append("CPUExecutionProvider")
        return ordered
    except Exception:
        return ["CPUExecutionProvider"]


@lru_cache(maxsize=1)
def device_summary(prefer: str = "auto") -> dict:
    """Resume cache : device + providers + precision rapide conseillee."""
    dev = torch_device(prefer)
    info = cuda_info()
    info["device"] = dev
    info["onnx_providers"] = onnx_providers(prefer_gpu=(dev != "cpu"))
    # precision : fp16/AMP sur CUDA (rapide + precis), fp32 ailleurs
    info["precision"] = "amp-fp16" if dev == "cuda" else ("fp16-mps" if dev == "mps" else "fp32")
    return info
