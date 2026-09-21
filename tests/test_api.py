"""Fast tests, no browser, no heavy models — 35+ types, API-only."""
import base64
import io
from fastapi.testclient import TestClient
from nocaptcha.server import create_app
from nocaptcha.ai.instructions import parse_instruction
from nocaptcha.ai.animated import vote_frames
from nocaptcha.ai.math_solver import solve_math_text
from nocaptcha.ai.slider import find_slider_gap, human_track
from nocaptcha.ai.rotate_click import estimate_rotation_angle, click_targets
from nocaptcha.ai.pow import solve_altcha
from nocaptcha.solvers import REGISTRY
from PIL import Image, ImageDraw

client = TestClient(create_app())

def _b64(img: Image.Image) -> str:
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def test_health():
    r = client.get("/v1/health")
    assert r.status_code == 200 and r.json()["ok"]

def test_capabilities_35():
    r = client.get("/v1/capabilities")
    assert r.status_code == 200
    types = {c["type"] for c in r.json()}
    for t in ["recaptcha-v2", "recaptcha-v3", "recaptcha-enterprise", "hcaptcha", "turnstile",
              "funcaptcha", "arkose", "amazon-captcha", "altcha", "friendly-captcha", "cutcaptcha",
              "datadome-captcha", "mtcaptcha", "geetest", "captchafox", "vk-captcha",
              "prosopo-procaptcha", "atb-captcha", "lemin-captcha", "capy-puzzle", "temu-captcha",
              "rotate-captcha", "normal-captcha", "russian-captcha", "chinese-captcha",
              "number-captcha", "click-captcha", "math-captcha", "slider-captcha", "text-captcha",
              "imperva-captcha", "binance-captcha", "tencent-captcha", "image-captcha", "audio-captcha"]:
        assert t in types, f"manquant: {t}"
    assert len(types) >= 35

def test_registry_covers_enum():
    from nocaptcha.models import CaptchaType
    for ct in CaptchaType:
        assert ct.value in REGISTRY, f"REGISTRY sans {ct.value}"

def test_openapi_json():
    r = client.get("/v1/openapi.json")
    assert r.status_code == 200 and "paths" in r.json()
    paths = r.json()["paths"]
    for p in ["/v1/solve", "/v1/solve/image", "/v1/solve/ocr", "/v1/solve/slider",
              "/v1/solve/rotate", "/v1/solve/click", "/v1/solve/pow", "/v1/solve/math"]:
        assert p in paths, p

def test_parse_fr_en():
    assert parse_instruction("Sélectionnez tous les feux de circulation")["target_en"] == "traffic light"
    assert parse_instruction("Select all images with crosswalks")["target_en"] == "crosswalk"
    assert parse_instruction("Cliquez sur chaque bus")["target_en"] == "bus"

def test_vote_frames():
    assert vote_frames([(True, .9), (True, .6), (False, .4)])[0] is True

def test_math_solver():
    assert solve_math_text("2 + 3 = ?")[0] == "5"
    assert solve_math_text("cinq x 4")[0] == "20"
    assert solve_math_text("12 - 7")[0] == "5"
    assert solve_math_text("10 / 4")[0] == "2.5"

def test_slider_gap_synthetic():
    bg = Image.new("RGB", (300, 150), "gray")
    d = ImageDraw.Draw(bg)
    d.rectangle([180, 40, 230, 110], fill="black")  # trou
    x, conf, w = find_slider_gap(bg, None)
    assert w == 300 and 100 < x < 260 and conf > 0
    assert len(human_track(120)) > 5

def test_rotate_click():
    img = Image.new("RGB", (120, 120), "white")
    angle, conf = estimate_rotation_angle(img)
    assert 0 <= angle < 360 and 0 <= conf <= 1.0
    coords, c2, via = click_targets(Image.new("RGB", (90, 90), "white"), "car")
    assert isinstance(coords, list) and isinstance(via, str)

def test_pow_demo():
    n, conf, ms = solve_altcha("abc", "salt-demo", maxnumber=5000)
    assert isinstance(ms, int)  # peut etre None si difficulte haute, pas d'echec

def test_solve_image_heuristic():
    b64 = _b64(Image.new("RGB", (100, 100), "white"))
    r = client.post("/v1/solve/image", json={"instruction": "Select all cars",
        "images": [{"id": 0, "image_b64": b64}]})
    assert r.status_code == 200 and "selected_ids" in r.json()

def test_universal_ocr_kinds():
    b64 = _b64(Image.new("RGB", (120, 40), "white"))
    for kind in ["auto", "normal", "number", "math"]:
        r = client.post("/v1/solve/ocr", json={"image_b64": b64, "kind": kind})
        assert r.status_code == 200, kind

def test_universal_slider_rotate_click_math_pow():
    bg = Image.new("RGB", (300, 150), "gray")
    d = ImageDraw.Draw(bg); d.rectangle([180, 40, 230, 110], fill="black")
    b64bg = _b64(bg)
    r = client.post("/v1/solve/slider", json={"bg_b64": b64bg})
    assert r.status_code == 200 and "coords" in r.json()
    r = client.post("/v1/solve", json={"type": "slider-captcha", "image_b64": b64bg})
    assert r.status_code == 200
    r = client.post("/v1/solve/rotate", json={"image_b64": _b64(Image.new("RGB", (100, 100), "white"))})
    assert r.status_code == 200
    r = client.post("/v1/solve/click", json={"image_b64": _b64(Image.new("RGB", (90, 90), "white")), "instruction": "Cliquez sur les bus"})
    assert r.status_code == 200
    r = client.post("/v1/solve/math", json={"text": "2+3=?"})
    assert r.status_code == 200 and r.json()["text"] == "5"
    r = client.post("/v1/solve/pow", json={"type": "altcha", "challenge": "demo", "salt": "s", "maxnumber": 2000})
    assert r.status_code == 200

def test_human_mouse_path():
    from nocaptcha.browser.human import human_path, human_timing
    pts = human_path(0, 0, 200, 100, seed=42)
    assert len(pts) >= 12
    assert pts[-1][0] > 150  # arrive pres de la cible
    assert 0.1 < human_timing(200, seed=1) < 3.0

def test_stats_avg_seconds():
    client.post("/v1/stats/reset")
    r = client.post("/v1/solve/math", json={"text": "1+1=?"})
    assert r.status_code == 200
    s = client.get("/v1/stats").json()
    assert s["total"] >= 1 and "avg_s" in s
    assert isinstance(s["avg_s"], (int, float))
    assert "math-captcha" in s["by_type"]

def test_no_rate_limit_burst():
    # 20 requetes locales d'affilee : aucune 429 (0 rate-limit API)
    for _ in range(20):
        r = client.post("/v1/solve/math", json={"text": "2+2=?"})
        assert r.status_code == 200
        assert r.status_code != 429
    lim = client.get("/v1/limits").json()
    assert lim["api_rate_limit"] == "none"

def test_learn_capture_and_train():
    from nocaptcha.learn import save_capture, recall, train_summary
    img = Image.new("RGB", (64, 32), "white")
    d = ImageDraw.Draw(img); d.text((5, 5), "AB12", fill="black")
    b64 = _b64(img)
    p = save_capture("normal-captcha", b64, {"text": "AB12"}, ms=12, conf=0.9)
    assert p is None or isinstance(p, str)
    s = train_summary()
    assert "captures" in s and "by_type" in s
    r = client.get("/v1/dataset/summary")
    assert r.status_code == 200 and r.json()["ok"]
    r = client.post("/v1/dataset/train")
    assert r.status_code == 200 and r.json()["trained"] in (True, "bank")

def test_no_lab_api_only():
    # the HTML lab is gone: API-only service
    r = client.get("/lab")
    assert r.status_code == 404
    r = client.get("/")
    body = r.json()
    assert body["service"] == "nocaptcha" and "lab" not in body

def test_onnx_zoo_offline_safe():
    from nocaptcha.ai import onnx_zoo as z
    assert set(z.REGISTRY) >= {"mnist-12", "mobilenetv2-12-int8", "synset"}
    assert isinstance(z.is_cached("mnist-12"), bool)
    assert z.ensure("modele-inexistant") is None
    d, c = z.mnist_digit(Image.new("RGB", (28, 28), "white"))
    assert (d is None and c == 0.0) or (isinstance(d, int) and 0 <= d <= 9)
    m, mc = z.mobilenet_contains(Image.new("RGB", (64, 64), "white"), "bus")
    assert isinstance(m, bool) and 0.0 <= mc <= 1.0

def test_models_endpoints():
    r = client.get("/v1/models")
    assert r.status_code == 200 and r.json()["ok"] and "mnist-12" in r.json()["models"]
    assert "ddddocr" in r.json()["models"] and "warmup" in r.json()
    r = client.post("/v1/models/download", json={"name": "modele-inexistant"})
    assert r.status_code == 200 and r.json()["done"]["modele-inexistant"]["ok"] is False

def test_dddd_captcha_backends():
    from nocaptcha.ai import dddd
    assert dddd.available() is True
    t, c, v = dddd.classify(Image.new("RGB", (120, 40), "white"))
    assert isinstance(t, str) and 0.0 <= c <= 1.0 and "ddddocr" in v
    x, cx = dddd.slide_x(Image.new("RGB", (50, 50), "gray"), Image.new("RGB", (300, 150), "gray"))
    assert (x is None) or isinstance(x, int)

def test_slider_ensemble_keeps_gap():
    from nocaptcha.ai.slider import find_slider_gap_best
    bg = Image.new("RGB", (300, 150), "gray")
    d = ImageDraw.Draw(bg); d.rectangle([180, 40, 230, 110], fill="black")
    x, conf, w, via = find_slider_gap_best(bg, None)
    assert w == 300 and 100 < x < 260 and via == "opencv"

def test_ocr_uses_captcha_first_for_number():
    from nocaptcha.ai.ocr import LocalOcr
    o = LocalOcr("auto", "en", kind="number")
    assert o.active == "ddddocr"
    o2 = LocalOcr("auto", "en", kind="text")
    assert o2.active in ("rapidocr", "easyocr", "tesseract", "ddddocr")

def test_warmup_skips_missing_optional(capsys):
    import importlib.util
    from nocaptcha import resources
    st = resources.warmup_sync()
    assert st["finished"] is True
    yolo = st["items"]["yolo/yolov8n"]
    if importlib.util.find_spec("ultralytics") is None:
        assert yolo.get("skipped") is True and yolo["ok"] is False
        assert not any("yolo" in e for e in st["errors"])
        out = capsys.readouterr().out
        assert "[-] warmup finished with gaps" not in out
        assert "skipped (optional)" in out
    else:
        assert yolo["ok"] is True
    assert "ddddocr" in st["items"] and "onnx/mnist-12" in st["items"]
    r = client.get("/v1/models")
    assert r.json()["warmup"]["finished"] is True

def test_device_gpu_auto_fallback():
    from nocaptcha.learn.device import torch_device, device_summary, onnx_providers
    d = torch_device()
    assert d in ("cuda", "mps", "cpu")
    s = device_summary()
    assert s["device"] == d and "precision" in s and "onnx_providers" in s
    assert isinstance(onnx_providers(), list) and "CPUExecutionProvider" in onnx_providers()
    r = client.get("/v1/device")
    assert r.status_code == 200 and r.json()["ok"] and r.json()["device"] in ("cuda", "mps", "cpu")

def test_trainer_no_torch_graceful():
    import importlib.util
    if importlib.util.find_spec("torch") is not None:
        return  # machine GPU/dev : couvert par smoke CPU ci-dessous
    from nocaptcha.learn.trainer import train_classifier
    rep = train_classifier("amazon-captcha", epochs=1)
    assert rep["ok"] is False and "torch" in rep["error"].lower()

def test_train_bank_and_classifier_endpoints():
    r = client.post("/v1/dataset/train", json={})
    assert r.status_code == 200 and r.json()["ok"]
    r = client.post("/v1/dataset/train", json={"type": "amazon-captcha", "epochs": 1, "batch": 8})
    assert r.status_code == 200  # ok False si pas de data/torch, mais 200 + report
    assert "report" in r.json()

def test_universal_validation():
    # type is required
    r = client.post("/v1/solve", json={})
    assert r.status_code == 422
    # unknown type rejected
    r = client.post("/v1/solve", json={"type": "nope-captcha"})
    assert r.status_code in (404, 422)
    # unreadable base64 rejected
    r = client.post("/v1/solve", json={"type": "amazon-captcha", "image_b64": "!!!not-base64!!!"})
    assert r.status_code == 400

def test_solve_file_multipart():
    buf = io.BytesIO(); Image.new("RGB", (120, 40), "white").save(buf, format="PNG")
    r = client.post("/v1/solve/file", data={"type": "amazon-captcha"},
                    files={"file": ("captcha.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200 and r.json()["type"] == "amazon-captcha"
    # missing type -> 422
    buf.seek(0)
    r = client.post("/v1/solve/file", files={"file": ("c.png", buf.getvalue(), "image/png")})
    assert r.status_code == 422
    # garbage file -> 400
    r = client.post("/v1/solve/file", data={"type": "amazon-captcha"},
                    files={"file": ("c.txt", b"not an image", "text/plain")})
    assert r.status_code == 400

def test_openapi_has_universal_file():
    paths = client.get("/v1/openapi.json").json()["paths"]
    assert "/v1/solve/file" in paths

def test_nocap_logging_convention(capsys):
    from nocaptcha.log import banner, ok, err, info, NOCAP_BANNER
    assert "NoCap" in NOCAP_BANNER
    banner(); ok("good"); err("bad"); info("hint")
    out = capsys.readouterr().out
    assert "[+]" in out and "[-]" in out and "[\\]" in out

def test_python_sdk_payloads(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, "sdks/python")
    from nocaptcha_client import NoCaptchaClient, image_to_b64
    p = tmp_path / "c.png"
    Image.new("RGB", (10, 10), "white").save(p)
    assert image_to_b64(str(p))  # file path -> b64
    assert image_to_b64(b"rawbytes")  # bytes -> b64
    try:
        image_to_b64("https://x/y.png")
        assert False, "URLs must go through image_url"
    except ValueError:
        pass
    seen = {}
    api = NoCaptchaClient()
    # payload shape check via solve() with monkeypatched transport (no network)
    monkeypatch.setattr(api, "_post_json", lambda path, payload: seen.update(path=path, payload=payload) or {"ok": True})
    api.solve("amazon-captcha", image=str(p))
    assert seen["path"] == "/v1/solve" and seen["payload"]["type"] == "amazon-captcha"
    assert seen["payload"]["image_b64"]
