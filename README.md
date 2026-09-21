# NoCaptcha — local captcha-solving API (35+ types, 100% offline)

```
 _   _      ____
| \ | | ___/ ___|__ _ _ __
|  \| |/ _ \ |   / _` | '_ \
| |\  | (_) | |_| (_| | |_) |
|_| \_|\___/ \___\__,_| .__/
                       |_|
 NoCap - local captcha solver
```

**One universal API for every captcha: send `type` + image (base64, file upload
or URL) and get the answer back.** Token-based captchas (hCaptcha, reCAPTCHA,
Turnstile…) are solved in a stealth Playwright browser — your bot just injects
the returned token. No cloud, no key, no rate-limit.

> **Honest accuracy note.** No local tool solves everything perfectly — especially
> hCaptcha/reCAPTCHA image grids, which are adversarial by design. NoCaptcha layers
> the best offline models available (ddddocr for text captchas, YOLOv8 + MobileNet
> + CLIP + OpenCV for images, template bank + self-trained classifier for repeats)
> and always reports `confidence` so your program can retry or escalate.
> Typical local results: text/number captchas ~90%+, sliders high, image grids
> variable (40–80% depending on the target class).

## Quickstart

```bash
pip install ".[ai-light,browser]"
playwright install chromium
python -m nocaptcha warmup   # preload everything once (also auto-runs at serve)
python -m nocaptcha serve --port 7888
# Docs : http://127.0.0.1:7888/v1/docs
# JSON : http://127.0.0.1:7888/v1/openapi.json
```

```bash
# image captcha, 3 equivalent ways
curl -X POST http://127.0.0.1:7888/v1/solve \
  -H "Content-Type: application/json" \
  -d '{"type":"amazon-captcha","image_b64":"..."}'

curl -X POST http://127.0.0.1:7888/v1/solve/file \
  -F "type=amazon-captcha" -F "file=@captcha.png"

curl -X POST http://127.0.0.1:7888/v1/solve \
  -H "Content-Type: application/json" \
  -d '{"type":"amazon-captcha","image_url":"https://.../captcha.png"}'

# browser token flow
curl -X POST http://127.0.0.1:7888/v1/solve \
  -H "Content-Type: application/json" \
  -d '{"type":"hcaptcha","sitekey":"xxx","url":"https://example.com"}'
# -> {"ok":true,"token":"P1_...","ms":12340,...}  (inject it, see below)
```

## The universal contract

Every solve goes through `POST /v1/solve` (JSON) or `POST /v1/solve/file`
(multipart). **`type` is always required** — list values at `GET /v1/capabilities`.

| Send the image as | Field | Endpoint |
|---|---|---|
| base64 string | `image_b64` | `POST /v1/solve` |
| remote URL (fetched server-side, no CORS) | `image_url` | `POST /v1/solve` |
| raw file upload | `file` (+ optional `file2` piece) | `POST /v1/solve/file` |

Response shape (always the same):

```json
{ "ok": true, "type": "amazon-captcha", "ms": 231,
  "text": "AB12", "token": null, "coords": null, "selected_ids": null,
  "confidence": 0.8, "detail": { "backend": "ddddocr" } }
```

Exactly one of `text` / `token` / `coords` / `selected_ids` carries the answer:

| Answer field | Types |
|---|---|
| `text` | all OCR kinds, `math-captcha`, `audio` |
| `coords` | `slider-captcha` → `[x]` (+`detail.track`), `rotate-captcha` → `[angle]`, `click-captcha` → `[x1,y1,...]` 0-1000 |
| `selected_ids` | `image-select`, `image-captcha` (grid tiles to click) |
| `token` | `hcaptcha`, `recaptcha-v2/v3`, `turnstile`, `funcaptcha`, PoW types, … |

## Token flow (bots, account creators, checkers)

For widget captchas your program never touches pixels — NoCaptcha drives a
stealth browser and hands you the token plus the exact injection point:

1. Read the widget `sitekey` from the page (or pass it if you know it).
2. `POST /v1/solve {"type","sitekey","url"}` → `{"token": "..."}`.
3. Set the token field, then submit the form.

| Provider | `type` | Token field | Post-injection |
|---|---|---|---|
| hCaptcha | `hcaptcha` | `[name=h-captcha-response]` | submit form |
| reCAPTCHA v2 | `recaptcha-v2` | `#g-recaptcha-response` | submit form |
| reCAPTCHA v3 | `recaptcha-v3` | returned directly | send with your `action` |
| Turnstile | `turnstile` | `[name=cf-turnstile-response]` | submit form |

Ready-to-run examples (adapt selectors/URL to your target):
`examples/hcaptcha-token-flow.py` (Python+Playwright),
`examples/hcaptcha-token-flow.js` (Node+Playwright).
Only automate sites you own or that allow it.

## All endpoints

| Method | Endpoint | Use |
|---|---|---|
| GET | `/v1/health` | ping + version |
| GET | `/v1/capabilities` | all supported types |
| POST | `/v1/solve` | **universal** (JSON: `type` + `image_b64`/`image_url` or `sitekey`+`url` or `data.challenge`) |
| POST | `/v1/solve/file` | **universal** (multipart: `type` + `file` [+`file2`,`instruction`]) |
| POST | `/v1/solve/image` | grid `{instruction, images[{id,image_b64\|image_url}], animated}` → `selected_ids` |
| POST | `/v1/solve/ocr` | OCR `{image_b64\|image_url, kind, langs}` → `text` |
| POST | `/v1/solve/ocr-upload` | OCR multipart file |
| POST | `/v1/solve/audio` | audio transcription → `text` |
| POST | `/v1/solve/slider` | `{bg_b64, piece_b64}` → `coords:[x]` + human `track` |
| POST | `/v1/solve/rotate` | `{image}` → `coords:[angle]` |
| POST | `/v1/solve/click` | `{image, instruction}` → coords 0-1000 |
| POST | `/v1/solve/pow` | `{type, challenge, salt, maxnumber}` → `token` |
| POST | `/v1/solve/math` | `{image\|text}` → answer `text` |
| GET | `/v1/stats` | avg seconds, p50/p95, success per type |
| POST | `/v1/stats/reset` | reset counters |
| GET | `/v1/device` | GPU/CPU device + ONNX providers |
| GET | `/v1/models` | model cache + warmup status |
| POST | `/v1/models/download` | download + preload all |
| GET | `/v1/dataset/summary` | auto-learn bank state |
| POST | `/v1/dataset/train` | train classifier (GPU when available) |
| GET | `/v1/limits` | rate-limit proof (`none`) |
| GET | `/v1/openapi.json`, `/v1/docs.json` | machine docs |
| GET | `/v1/docs` | Swagger UI |

Full reference with curl/Python/Node examples per endpoint: [`docs/API.md`](docs/API.md).

## Supported types (39 values)

`recaptcha-v2`, `recaptcha-v3`, `recaptcha-enterprise`, `hcaptcha`, `turnstile`,
`funcaptcha`, `arkose`, `geetest`, `geetest-v4`, `image-select`, `image-captcha`,
`image-text`, `normal-captcha`, `text-captcha`, `number-captcha`,
`russian-captcha`, `chinese-captcha`, `amazon-captcha`, `vk-captcha`,
`atb-captcha`, `math-captcha`, `click-captcha`, `audio`, `audio-captcha`,
`slider-captcha`, `rotate-captcha`, `cutcaptcha`, `capy-puzzle`, `temu-captcha`,
`lemin-captcha`, `binance-captcha`, `tencent-captcha`, `altcha`,
`friendly-captcha`, `captchafox`, `mtcaptcha`, `prosopo-procaptcha`,
`datadome-captcha`, `imperva-captcha`

## SDKs (zero dependencies)

- Python (stdlib only): `sdks/python/nocaptcha_client.py`
- Node.js (fetch, Node 18+): `sdks/nodejs/nocaptcha.js`

```python
from nocaptcha_client import NoCaptchaClient
api = NoCaptchaClient()
print(api.solve("amazon-captcha", image="captcha.png")["text"])
print(api.token("hcaptcha", sitekey="xxx", url="https://example.com")["token"])
```
```js
const { NoCaptchaClient } = require('./sdks/nodejs/nocaptcha');
const api = new NoCaptchaClient();
console.log((await api.solve({ type: 'amazon-captcha', image: 'captcha.png' })).text);
```
Details: [`sdks/README.md`](sdks/README.md).

## CLI

```
nocaptcha serve | solve | solve-file | solve-image | solve-text | ocr
          solve-slider | solve-rotate | solve-click | solve-math | solve-pow
          capabilities | doctor | stats | train | device | models | warmup
          bench | docs | version
```

Startup prints the NoCap ASCII banner and uses the log convention
`[+]` success / `[-]` failure / `[\]` hint — same lines as the server logs.

## How it solves (local stack)

1. **Stealth Chromium (Playwright)** — masked webdriver, spoofed WebGL, random
   viewport/UA/locale, humanized Bézier mouse, pooled contexts.
2. **Text captchas** — ddddocr (captcha-trained, GitHub `sml2h3/ddddocr`)
   → RapidOCR → EasyOCR → Tesseract + CLAHE + recall bank.
3. **Image grids** — YOLOv8n detection → CLIP zero-shot → MobileNet int8 →
   OpenCV heuristics + animated vote; EN+FR instruction parsing.
4. **Sliders/puzzles** — OpenCV gap ensemble with ddddocr `slide_match`
   + human drag trajectory; rotate/click solvers included.
5. **PoW** — Altcha/Friendly/CaptchaFox/Prosopo computed locally.
6. **Self-learning** — every OK solve is captured; template recall (<5ms) and an
   optional GPU classifier improve repeats. GPU (CUDA/MPS) auto-used for
   EasyOCR, YOLO, CLIP and training; CPU fallback everywhere.

At boot the server downloads + preloads all optimal resources in the background
(ONNX zoo, ddddocr, RapidOCR, YOLOv8n) — see `GET /v1/models`.
Missing *optional* dependencies (e.g. YOLO without `pip install ".[ai-full]"`)
are reported as `SKIP`, never as errors — every solver has a fallback chain.

## Configuration (env `NOCAPTCHA_*`)

`host`, `port` (7888), `browser_backend` (playwright|selenium), `headless`,
`detector_backend`, `ocr_backend`, `ocr_langs`, `device` (auto|cuda|mps|cpu),
`learn_enabled`, `solve_timeout`, `max_concurrent_solves`.

## Docker

```bash
docker compose up --build
```

## Contributing

See CONTRIBUTING.md. MIT.
