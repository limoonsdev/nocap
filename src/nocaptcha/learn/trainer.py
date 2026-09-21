"""Entrainement GPU (quand dispo) sur les captchas deja resolus.

Strategie precision + vitesse :
- Classifieur CNN leger (vocabulaire ferme : les N solutions les plus frequentes
  du type, ex: captchas numeriques/amazon revus) — parfait quand les memes
  challenges reviennent, ce qui est le cas dominant en production.
- GPU auto (CUDA > MPS > CPU), AMP fp16 sur CUDA, DataLoader batch + workers +
  pin_memory, ONNX export pour inference rapide.
- Sans torch installe : erreur explicite + fallback banque templates (CPU).
- Vocabulaire ouvert (texte arbitraire) : reste sur OCR moteur (qui lui-meme
  utilise le GPU si dispo, voir ai/ocr.py) + recall.

Usage :
    python -m nocaptcha train --type amazon-captcha --epochs 12
    POST /v1/dataset/train {"type": "amazon-captcha", "epochs": 12}
"""
from __future__ import annotations
import io
import json
import time
from pathlib import Path
from PIL import Image

from ..config import get_settings
from .device import torch_device, device_summary

IMG_SIZE = (128, 128)
MAX_CLASSES = 200
MIN_PER_CLASS = 2


def _captures_of(type_: str) -> list[dict]:
    s = get_settings()
    base = s.learn_dir if str(s.learn_dir) else (s.models_dir / "captures")
    mp = Path(base) / "manifest.jsonl"
    out = []
    if not mp.exists():
        return out
    for line in mp.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
            if e.get("type") == type_ and e.get("solution", {}).get("text"):
                out.append(e)
        except Exception:
            continue
    return out


def _load_img(base: Path, type_: str, fname: str) -> Image.Image | None:
    try:
        p = base / type_ / fname
        return Image.open(p).convert("RGB")
    except Exception:
        return None


def train_classifier(type_: str = "amazon-captcha", epochs: int = 10, batch: int = 64,
                     lr: float = 3e-3, device: str = "auto", amp: bool = True,
                     max_classes: int = MAX_CLASSES) -> dict:
    """Entraine le classifieur ferme sur GPU si dispo. Retourne le rapport."""
    t0 = time.time()
    dev = torch_device(device)
    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset
    except Exception:
        return {"ok": False, "device": dev, "error": "torch manquant : installez l'extra gpu (voir README)",
                "hint": "fallback : banque templates CPU toujours active"}
    import numpy as np

    s = get_settings()
    base = Path(s.learn_dir if str(s.learn_dir) else (s.models_dir / "captures"))
    rows = _captures_of(type_)
    if len(rows) < 4:
        return {"ok": False, "device": dev, "error": f"pas assez de captures ({len(rows)}<4) pour {type_}",
                "hint": "resolvez d'abord des captchas (auto-capture), puis relancez train"}

    # vocabulaire ferme : solutions les plus frequentes avec >=2 exemples
    from collections import Counter
    freq = Counter(r["solution"]["text"] for r in rows)
    labels = [t for t, c in freq.most_common(max_classes) if c >= MIN_PER_CLASS]
    if len(labels) < 2:
        return {"ok": False, "device": dev, "error": "vocabulaire ferme insuffisant (<2 classes x2 exemples)",
                "hint": "le recall templates reste actif ; accumulez plus de resolutions"}
    lab2id = {t: i for i, t in enumerate(labels)}

    X, y = [], []
    for r in rows:
        txt = r["solution"]["text"]
        if txt not in lab2id:
            continue
        img = _load_img(base, type_, r["file"])
        if img is None:
            continue
        img = img.resize(IMG_SIZE, Image.BILINEAR)
        X.append(np.asarray(img, dtype=np.float32).transpose(2, 0, 1) / 255.0)
        y.append(lab2id[txt])
    if len(X) < 4:
        return {"ok": False, "device": dev, "error": "images illisibles"}
    X = np.stack(X).astype(np.float32)
    y = np.array(y, dtype=np.int64)

    # split train/val stratifie simple (shuffle + 80/20)
    rng = np.random.default_rng(7)
    idx = rng.permutation(len(X))
    cut = max(1, int(len(X) * 0.8))
    tr, va = idx[:cut], idx[cut:]
    if len(va) == 0:
        tr, va = idx, idx[-1:]

    # normalisation moyenne/std ImageNet-lite (stabilise + precise)
    mean = X[tr].mean(axis=(0, 2, 3), keepdims=True)
    std = X[tr].std(axis=(0, 2, 3), keepdims=True) + 1e-6
    Xn = (X - mean) / std

    device_t = torch.device(dev if dev in ("cuda", "mps", "cpu") else "cpu")
    pin = dev == "cuda"
    workers = 4 if dev == "cuda" else 0
    train_ds = TensorDataset(torch.from_numpy(Xn[tr]), torch.from_numpy(y[tr]))
    val_ds = TensorDataset(torch.from_numpy(Xn[va]), torch.from_numpy(y[va]))
    train_ld = DataLoader(train_ds, batch_size=min(batch, len(train_ds)), shuffle=True,
                          num_workers=workers, pin_memory=pin)
    val_ld = DataLoader(val_ds, batch_size=min(batch, len(val_ds)),
                        num_workers=workers, pin_memory=pin)

    class TinyCNN(torch.nn.Module):
        def __init__(self, ncls: int):
            super().__init__()
            import torch.nn as nn
            def blk(ci, co):
                return nn.Sequential(nn.Conv2d(ci, co, 3, padding=1, bias=False),
                                     nn.BatchNorm2d(co), nn.ReLU(inplace=True),
                                     nn.Conv2d(co, co, 3, padding=1, bias=False),
                                     nn.BatchNorm2d(co), nn.ReLU(inplace=True),
                                     nn.MaxPool2d(2))
            self.f = nn.Sequential(blk(3, 32), blk(32, 64), blk(64, 128),
                                   nn.AdaptiveAvgPool2d(1), nn.Flatten(),
                                   nn.Dropout(0.2), nn.Linear(128, 128), nn.ReLU(inplace=True))
            self.head = nn.Linear(128, ncls)
        def forward(self, x):
            return self.head(self.f(x))

    model = TinyCNN(len(labels)).to(device_t)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, epochs))
    lossf = torch.nn.CrossEntropyLoss(label_smoothing=0.05)  # precision : robuste aux labels bruites
    use_amp = bool(amp and dev == "cuda")
    scaler = torch.amp.GradScaler("cuda") if use_amp else None

    best_acc, best_state, samples = 0.0, None, 0
    for ep in range(max(1, epochs)):
        model.train()
        for xb, yb in train_ld:
            xb, yb = xb.to(device_t, non_blocking=pin), yb.to(device_t, non_blocking=pin)
            opt.zero_grad(set_to_none=True)
            if use_amp:
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    out = model(xb)
                    loss = lossf(out, yb)
                scaler.scale(loss).backward()
                scaler.step(opt)
                scaler.update()
            else:
                loss = lossf(model(xb), yb)
                loss.backward()
                opt.step()
            samples += len(xb)
        sched.step()
        # validation (batch, rapide)
        model.eval()
        correct = tot = 0
        with torch.no_grad():
            for xb, yb in val_ld:
                xb = xb.to(device_t, non_blocking=pin)
                pred = model(xb).argmax(1).cpu()
                correct += int((pred == yb).sum())
                tot += len(yb)
        acc = correct / max(1, tot)
        if acc >= best_acc:
            best_acc = acc
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)
    out_dir = base / type_
    out_dir.mkdir(parents=True, exist_ok=True)
    pt_path = out_dir / "model.pt"
    torch.save({"state": model.state_dict(), "labels": labels,
                "mean": mean.squeeze().tolist(), "std": std.squeeze().tolist(),
                "img": list(IMG_SIZE), "acc": best_acc}, str(pt_path))
    # export ONNX (inference GPU/CPU rapide)
    onnx_path = out_dir / "model.onnx"
    onnx_ok = False
    try:
        dummy = torch.randn(1, 3, *IMG_SIZE)
        torch.onnx.export(model.cpu().eval(), dummy, str(onnx_path),
                          input_names=["input"], output_names=["logits"],
                          dynamic_axes={"input": {0: "batch"}}, opset_version=17)
        onnx_ok = onnx_path.exists()
    except Exception:
        pass

    dt = time.time() - t0
    report = {"ok": True, "type": type_, "device": dev,
              "precision": "amp-fp16" if use_amp else "fp32",
              "epochs": epochs, "classes": len(labels), "train_n": len(tr), "val_n": len(va),
              "val_acc": round(best_acc, 4), "seconds": round(dt, 2),
              "samples_per_s": round(samples / max(dt, 1e-6), 1),
              "model": str(pt_path), "onnx": str(onnx_path) if onnx_ok else None}
    try:
        (out_dir / "train_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception:
        pass
    return report


def predict_classifier(type_: str, img: Image.Image) -> tuple[str | None, float]:
    """Inference rapide via model.pt (GPU si dispo). Retourne (texte, conf) ou (None, 0)."""
    try:
        import torch
        s = get_settings()
        base = Path(s.learn_dir if str(s.learn_dir) else (s.models_dir / "captures"))
        pt = base / type_ / "model.pt"
        if not pt.exists():
            return None, 0.0
        ckpt = torch.load(str(pt), map_location="cpu", weights_only=False)
        labels: list = ckpt["labels"]
        dev = torch_device(getattr(s, "device", "auto"))
        device_t = torch.device(dev if dev in ("cuda", "mps", "cpu") else "cpu")

        class TinyCNN(torch.nn.Module):
            def __init__(self, ncls: int):
                super().__init__()
                import torch.nn as nn
                def blk(ci, co):
                    return nn.Sequential(nn.Conv2d(ci, co, 3, padding=1, bias=False),
                                         nn.BatchNorm2d(co), nn.ReLU(inplace=True),
                                         nn.Conv2d(co, co, 3, padding=1, bias=False),
                                         nn.BatchNorm2d(co), nn.ReLU(inplace=True),
                                         nn.MaxPool2d(2))
                self.f = nn.Sequential(blk(3, 32), blk(32, 64), blk(64, 128),
                                       nn.AdaptiveAvgPool2d(1), nn.Flatten(),
                                       nn.Dropout(0.2), nn.Linear(128, 128), nn.ReLU(inplace=True))
                self.head = nn.Linear(128, ncls)
            def forward(self, x):
                return self.head(self.f(x))

        model = TinyCNN(len(labels))
        model.load_state_dict(ckpt["state"])
        model.to(device_t).eval()
        import numpy as np
        arr = np.asarray(img.convert("RGB").resize(tuple(ckpt.get("img", [128, 128])), Image.BILINEAR),
                         dtype=np.float32).transpose(2, 0, 1) / 255.0
        mean = np.array(ckpt["mean"], dtype=np.float32).reshape(3, 1, 1)
        std = np.array(ckpt["std"], dtype=np.float32).reshape(3, 1, 1)
        xb = torch.from_numpy(((arr - mean) / (std + 1e-6))[None]).to(device_t)
        use_amp = dev == "cuda"
        with torch.no_grad():
            if use_amp:
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    logits = model(xb)
            else:
                logits = model(xb)
            prob = torch.softmax(logits.float(), 1)[0]
            conf, idx = float(prob.max()), int(prob.argmax())
        return labels[idx], conf
    except Exception:
        return None, 0.0
