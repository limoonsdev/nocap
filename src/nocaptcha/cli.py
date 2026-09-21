"""NoCaptcha CLI — Typer + Rich (Windows cp1252-safe ASCII). 35+ types."""
from __future__ import annotations
import base64
import json
import pathlib
from typing import Optional
import typer
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import track

from . import __version__
from .config import get_settings
from .log import banner

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich",
                  help="NoCaptcha — fast local open-source captcha solver (35+ types).")
console = Console(legacy_windows=False)

OK, KO, WARN, INFO = "[green]OK[/]", "[red]KO[/]", "[yellow]!![/]", "[cyan]>>[/]"

def _api(base: str | None, port: int | None) -> str:
    s = get_settings()
    p = port or s.port
    return (base or f"http://127.0.0.1:{p}").rstrip("/")

def _b64(src: str) -> str:
    if src.startswith("http"):
        return base64.b64encode(httpx.get(src, timeout=20, follow_redirects=True).content).decode()
    return base64.b64encode(pathlib.Path(src).read_bytes()).decode()

def _show(data: dict, title: str):
    if data.get("ok"):
        console.print(Panel.fit(
            f"{OK} [green]{title} in {data.get('ms')}ms[/]\n"
            f"[bold]{data.get('text') or data.get('token') or data.get('coords') or data.get('selected_ids')}[/]\n"
            f"[dim]{json.dumps(data.get('detail', {}), ensure_ascii=False)[:600]}[/]", title=title))
    else:
        console.print(Panel.fit(f"{KO} [red]Failed[/]\n{json.dumps(data, ensure_ascii=False)[:800]}", title=title))
        raise typer.Exit(1)

@app.command()
def serve(host: Optional[str] = None, port: Optional[int] = None):
    """Start the local API: http://localhost:PORT/v1/..."""
    from .server import run
    s = get_settings()
    h, p = host or s.host, port or s.port
    s.host, s.port = h, p  # keep /v1/health truthful when flags override env
    banner()
    console.print(Panel.fit(
        f"[bold cyan]NoCaptcha v{__version__} — 35+ types[/]\n{INFO} API : [green]http://{h}:{p}/v1/docs[/]\n{INFO} JSON : [green]http://{h}:{p}/v1/openapi.json[/]",
        title="NoCaptcha serve"))
    run(host=h, port=p)

@app.command()
def capabilities(api: Optional[str] = None, port: Optional[int] = None):
    """List the 35+ supported captchas."""
    url = _api(api, port) + "/v1/capabilities"
    data = httpx.get(url, timeout=15).json()
    table = Table(title=f"NoCaptcha — {len(data)} local types", show_lines=True)
    table.add_column("Type"); table.add_column("Method"); table.add_column("Local"); table.add_column("Notes")
    for c in data:
        table.add_row(c["type"], c["method"], OK if c["local"] else WARN, c.get("notes", "")[:90])
    console.print(table)

@app.command()
def solve(type: str = typer.Option(..., help="recaptcha-v2, hcaptcha, turnstile, tencent-captcha, amazon-captcha, altcha... (see capabilities)"),
          url: str = typer.Option("", help="Page URL"),
          sitekey: str = typer.Option("", help="Sitekey when required"),
          image: Optional[str] = typer.Option(None, help="Image (OCR/slider/rotate/click): path or URL"),
          image2: Optional[str] = typer.Option(None, help="Slider piece: path or URL"),
          instruction: Optional[str] = typer.Option(None, help="Instruction for click/image-select"),
          langs: str = typer.Option("fr,en"),
          action: str = typer.Option("homepage"),
          api: Optional[str] = None, port: Optional[int] = None, timeout: int = 90):
    """Solve ANY captcha (35+ types, 1 universal command)."""
    body: dict = {"type": type, "sitekey": sitekey or None, "url": url or None,
                  "action": action, "timeout": timeout, "langs": langs, "data": {}}
    if image: body["image_b64"] = _b64(image)
    if image2: body["image_b64_2"] = _b64(image2)
    if instruction: body["instruction"] = instruction
    with console.status(f"[cyan]Solving {type}...[/]", spinner="dots"):
        r = httpx.post(_api(api, port) + "/v1/solve", json=body, timeout=timeout + 15)
    try: data = r.json()
    except Exception:
        console.print(f"[red]HTTP {r.status_code}: {r.text[:500]}[/]"); raise typer.Exit(1)
    _show(data, type)

@app.command(name="solve-file")
def solve_file(type: str = typer.Option(..., help="Captcha type (see capabilities)"),
               file: str = typer.Option(..., help="Image file path"),
               file2: Optional[str] = typer.Option(None, help="Slider piece path"),
               instruction: Optional[str] = typer.Option(None, help="Instruction for click/image-select"),
               api: Optional[str] = None, port: Optional[int] = None, timeout: int = 90):
    """Solve ANY captcha from raw files (multipart upload, no base64 needed)."""
    with open(file, "rb") as f:
        files = {"file": (pathlib.Path(file).name, f.read(), "application/octet-stream")}
    data = {"type": type, "timeout": str(timeout)}
    if file2:
        with open(file2, "rb") as f:
            files["file2"] = (pathlib.Path(file2).name, f.read(), "application/octet-stream")
    if instruction: data["instruction"] = instruction
    with console.status(f"[cyan]Uploading + solving {type}...[/]", spinner="dots"):
        r = httpx.post(_api(api, port) + "/v1/solve/file", files=files, data=data, timeout=timeout + 15)
    _show(r.json(), type)

@app.command(name="solve-image")
def solve_image(instruction: str = typer.Option(...),
                images: list[str] = typer.Option(...),
                animated: bool = False, api: Optional[str] = None, port: Optional[int] = None):
    """Image grid (image-select/image-captcha/lemin)."""
    payload = [{"id": i, "image_b64": _b64(s)} for i, s in enumerate(track(images, description="Loading..."))]
    r = httpx.post(_api(api, port) + "/v1/solve/image",
                   json={"instruction": instruction, "images": payload, "animated": animated}, timeout=60)
    _show(r.json(), "image-select")

@app.command(name="solve-text")
def solve_text(image: str = typer.Option(...), kind: str = typer.Option("auto", help="auto|normal|text|number|russian|chinese|amazon|vk|atb|math"),
               langs: str = typer.Option("fr,en"), api: Optional[str] = None, port: Optional[int] = None):
    """OCR: normal/text/number/russian/chinese/amazon/vk/atb/math."""
    body = {"langs": langs, "kind": kind}
    body["image_b64" if not image.startswith("http") else "image_url"] = _b64(image) if not image.startswith("http") else image
    r = httpx.post(_api(api, port) + "/v1/solve/ocr", json=body, timeout=60)
    _show(r.json(), f"ocr/{kind}")

@app.command()
def ocr(image: str = typer.Option(...), api: Optional[str] = None, port: Optional[int] = None):
    """Quick OCR alias."""
    solve_text(image=image, kind="auto", api=api, port=port)

@app.command(name="solve-slider")
def solve_slider(bg: str = typer.Option(...), piece: Optional[str] = typer.Option(None),
                 api: Optional[str] = None, port: Optional[int] = None):
    """Slider (slider/cutcaptcha/capy/temu/binance/tencent) -> x + track."""
    body = {"bg_b64": _b64(bg)}
    if piece: body["piece_b64"] = _b64(piece)
    r = httpx.post(_api(api, port) + "/v1/solve/slider", json=body, timeout=60)
    _show(r.json(), "slider")

@app.command(name="solve-rotate")
def solve_rotate(image: str = typer.Option(...), api: Optional[str] = None, port: Optional[int] = None):
    """Rotate -> angle."""
    body = {"image_b64": _b64(image)} if not image.startswith("http") else {"image_url": image}
    r = httpx.post(_api(api, port) + "/v1/solve/rotate", json=body, timeout=60)
    _show(r.json(), "rotate")

@app.command(name="solve-click")
def solve_click(image: str = typer.Option(...), instruction: str = typer.Option(...),
                api: Optional[str] = None, port: Optional[int] = None):
    """Click -> coords 0-1000."""
    body = {"instruction": instruction}
    body["image_b64" if not image.startswith("http") else "image_url"] = _b64(image) if not image.startswith("http") else image
    r = httpx.post(_api(api, port) + "/v1/solve/click", json=body, timeout=60)
    _show(r.json(), "click")

@app.command(name="solve-math")
def solve_math(image: Optional[str] = typer.Option(None), text: Optional[str] = typer.Option(None),
               api: Optional[str] = None, port: Optional[int] = None):
    """Math: image or text ('2+3=?', 'five x 4')."""
    body: dict = {}
    if text: body["text"] = text
    if image: body["image_b64" if not image.startswith("http") else "image_url"] = _b64(image) if not image.startswith("http") else image
    r = httpx.post(_api(api, port) + "/v1/solve/math", json=body, timeout=60)
    _show(r.json(), "math")

@app.command(name="solve-pow")
def solve_pow(type: str = typer.Option("altcha"), challenge: str = typer.Option(...),
              salt: str = typer.Option(""), maxnumber: int = 100000,
              api: Optional[str] = None, port: Optional[int] = None):
    """PoW: altcha/friendly-captcha/captchafox/prosopo-procaptcha."""
    r = httpx.post(_api(api, port) + "/v1/solve/pow",
                   json={"type": type, "challenge": challenge, "salt": salt, "maxnumber": maxnumber}, timeout=120)
    _show(r.json(), f"pow/{type}")

@app.command()
def doctor():
    """Check Playwright, Chrome, Tesseract, AI models."""
    import shutil
    table = Table(title="NoCaptcha doctor (humanized Playwright)")
    table.add_column("Check"); table.add_column("Status"); table.add_column("Detail")
    table.add_row("Python", OK, __import__("sys").version.split()[0])
    try:
        from playwright.async_api import async_playwright
        table.add_row("Playwright", OK, "installed (chromium via: playwright install chromium)")
    except Exception:
        table.add_row("Playwright", WARN, "missing: pip install playwright && playwright install chromium")
    chrome = shutil.which("chrome") or shutil.which("chromium") or shutil.which("google-chrome") or shutil.which("msedge")
    table.add_row("Chrome/Chromium", OK if chrome else WARN, chrome or "optional (playwright ships chromium)")
    table.add_row("Tesseract", OK if shutil.which("tesseract") else WARN, "ok" if shutil.which("tesseract") else "OCR fallback")
    for mod in ["fastapi", "cv2", "PIL", "selenium", "playwright", "rapidocr_onnxruntime", "ultralytics", "transformers", "easyocr"]:
        try:
            __import__(mod); table.add_row(mod, OK, "installed")
        except Exception:
            table.add_row(mod, "--", "optional")
    console.print(table)
    try:
        from .learn.device import device_summary as _ds
        _d = _ds()
        console.print(f"[dim]Device: {_d['device']} - precision {_d['precision']} - onnx {_d['onnx_providers']}[/]")
    except Exception:
        pass
    console.print("[dim]Full setup: pip install '.[ai-light,browser]' && playwright install chromium[/]")
    console.print("[dim]GPU train: pip install '.[gpu]' (torch CUDA) - else auto CPU[/]")

@app.command()
def stats(api: Optional[str] = None, port: Optional[int] = None, reset: bool = False):
    """Show average speed (s), p50/p95, success per type."""
    base = _api(api, port)
    if reset:
        httpx.post(base + "/v1/stats/reset", timeout=10)
    data = httpx.get(base + "/v1/stats", timeout=15).json()
    console.print(Panel.fit(f"[bold]avg {data.get('avg_s')}s - success {data.get('success')} - n={data.get('total')}[/]",
                            title="Global stats"))
    table = Table(title="Average speed per type (seconds)")
    table.add_column("Type"); table.add_column("avg_s"); table.add_column("p50/p95"); table.add_column("success (n)")
    for k, v in (data.get("by_type") or {}).items():
        table.add_row(k, str(v.get("avg_s")), f"{v.get('p50_s')}/{v.get('p95_s')}", f"{v.get('success')} (n={v.get('n')})")
    console.print(table)

@app.command()
def train(type: str = typer.Option("", help="Type to train (empty = global bank + summary)"),
          epochs: int = typer.Option(10, help="Classifier epochs"),
          batch: int = typer.Option(64, help="Batch size (GPU: 64-256)"),
          device: str = typer.Option("auto", help="auto|cuda|mps|cpu"),
          amp: bool = typer.Option(True, help="AMP fp16 on CUDA (speed + accuracy)")):
    """Auto-train: bank + GPU classifier when available (fast and accurate)."""
    from .learn import train_summary
    from .learn.device import device_summary
    info = device_summary(device)
    console.print(Panel.fit(
        f"[bold]device {info['device']} - precision {info['precision']}[/]\n"
        f"[dim]torch {info.get('torch')} - gpu {info.get('gpu_names') or '-'} - onnx {info.get('onnx_providers')}[/]",
        title="Device"))
    s = train_summary()
    console.print(Panel.fit(f"[green]Captures: {s['captures']} - unique: {s['unique_hashes']} - dups: {s['duplicates']}[/]\n[dim]{s['dir']}[/]",
                            title="Bank"))
    for k, v in (s.get("by_type") or {}).items():
        console.print(f"  {k}: {v}")
    if type:
        from .learn.trainer import train_classifier
        with console.status(f"[cyan]Training {type} on {info['device']} (AMP={amp})...[/]", spinner="dots"):
            rep = train_classifier(type, epochs=epochs, batch=batch, device=device, amp=amp)
        if rep.get("ok"):
            console.print(Panel.fit(
                f"[green]val_acc {rep['val_acc']} - {rep['seconds']}s - {rep['samples_per_s']} ex/s[/]\n"
                f"[dim]{rep['model']} - onnx {rep.get('onnx')} - {rep['precision']} - classes {rep['classes']}[/]",
                title=f"Classifier {type}"))
        else:
            console.print(Panel.fit(f"[yellow]{rep.get('error')}[/]\n[dim]{rep.get('hint', '')}[/]",
                                    title=f"Classifier {type} (bank fallback)"))

@app.command()
def device():
    """Show detected device (GPU when available) + ONNX providers."""
    from .learn.device import device_summary
    import json as _j
    console.print(_j.dumps(device_summary(), indent=2, ensure_ascii=False))

@app.command()
def models(download: bool = typer.Option(False, help="Download missing models"),
           name: Optional[str] = typer.Option(None, help="Single model (mnist-12, mobilenetv2-12-int8, synset)")):
    """ONNX zoo: status + download (26 KB - 14 MB)."""
    from .ai.onnx_zoo import status, ensure, REGISTRY
    if download:
        names = [name] if name else list(REGISTRY.keys())
        for n in names:
            with console.status(f"[cyan]Downloading {n}...[/]", spinner="dots"):
                p = ensure(n)
            console.print(f"{OK if p else KO} {n} -> {p or 'failed (offline?)'}")
    table = Table(title="Lightweight ONNX models")
    table.add_column("Model"); table.add_column("Size"); table.add_column("State"); table.add_column("Usage")
    for k, v in status().items():
        sz = v["size"]
        szs = f"{sz/1048576:.1f} MB" if sz > 1048576 else (f"{sz/1024:.0f} KB" if sz > 1024 else f"{sz} o") if sz else "-"
        table.add_row(k, szs, OK if v["cached"] else WARN, v["desc"][:70])
    console.print(table)

@app.command()
def warmup():
    """Download + preload ALL optimal resources (same as server boot)."""
    from . import resources
    with console.status("[cyan]Warmup: ONNX + ddddocr + rapidocr + yolo...[/]", spinner="dots"):
        st = resources.warmup_sync()
    table = Table(title="Warmup resources")
    table.add_column("Resource"); table.add_column("State"); table.add_column("ms"); table.add_column("Detail")
    for k, v in st.get("items", {}).items():
        state = "[yellow]SKIP[/]" if v.get("skipped") else (OK if v["ok"] else KO)
        detail = v.get("detail", "")[:80].replace("[", "\\[")  # Rich would eat [ai-full] tags
        table.add_row(k, state, str(v["ms"]), detail)
    console.print(table)
    if st.get("errors"):
        for e in st["errors"]:
            console.print(f"{WARN} {str(e).replace('[', chr(92)+'[')}")
    dt = (st.get("finished_at", 0) - st.get("started_at", 0))
    console.print(f"[dim]Done in {dt:.1f}s. Next `serve` starts at full speed.[/]")

@app.command()
def bench(api: Optional[str] = None, port: Optional[int] = None, n: int = 5):
    """Local benchmark without browser: OCR/math/slider/rotate (avg seconds)."""
    import io, time as _t
    from PIL import Image
    base = _api(api, port)
    buf = io.BytesIO(); Image.new("RGB", (120, 40), "white").save(buf, format="PNG")
    import base64 as _b64
    b64 = _b64.b64encode(buf.getvalue()).decode()
    rows = []
    for i in range(n):
        t = _t.time()
        r = httpx.post(base + "/v1/solve/ocr", json={"image_b64": b64, "kind": "auto"}, timeout=60)
        rows.append(("ocr", (_t.time() - t), r.json().get("ok")))
    t = _t.time()
    r = httpx.post(base + "/v1/solve/math", json={"text": "2+3=?"}, timeout=30)
    rows.append(("math", _t.time() - t, r.json().get("text") == "5"))
    avg = sum(x[1] for x in rows) / max(1, len(rows))
    table = Table(title=f"Local bench n={len(rows)} — average {avg:.3f}s")
    table.add_column("Case"); table.add_column("s"); table.add_column("OK")
    for k, s_, ok in rows:
        table.add_row(k, f"{s_:.3f}", OK if ok else KO)
    console.print(table)

@app.command()
def docs(export: str = typer.Option("docs/API.json", help="OpenAPI JSON export path")):
    """Export the API documentation as JSON."""
    from .server import export_openapi
    p = export_openapi(export)
    console.print(f"[green]Documentation exported: {p}[/]")

@app.command()
def version():
    console.print(f"[cyan]NoCaptcha v{__version__} — humanized Playwright, 35+ types[/]")

if __name__ == "__main__":
    app()
