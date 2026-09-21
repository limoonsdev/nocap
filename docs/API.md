# NoCaptcha API reference

Base URL: `http://127.0.0.1:7888` (default). All endpoints live under `/v1`.
No auth, no rate-limit. Interactive docs: `GET /v1/docs` (Swagger),
machine docs: `GET /v1/openapi.json`.

Conventions used below:

```bash
API=http://127.0.0.1:7888
```

```python
from nocaptcha_client import NoCaptchaClient  # sdks/python, stdlib only
api = NoCaptchaClient()
```

```js
const { NoCaptchaClient } = require('./sdks/nodejs/nocaptcha');
const api = new NoCaptchaClient();
```

---

## Universal solving

### `POST /v1/solve` — solve anything (JSON)

**Body** (`application/json`):

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | **yes** | Captcha type (`GET /v1/capabilities`) |
| `image_b64` | string | * | Image as base64 (raw or `data:` URI) |
| `image_url` | string | * | Image URL, fetched server-side |
| `image_b64_2` | string | | Second image (slider piece) |
| `instruction` | string | | Instruction (`click-captcha`, grids) |
| `sitekey` | string | | Widget key (browser token flow) |
| `url` | string | | Page URL (browser token flow) |
| `langs` | string | | OCR languages, default `"fr,en"` |
| `timeout` | int | | Seconds, 5–600, default `90` |
| `data` | object | | Vendor payload (`challenge`,`salt`,…) |
| `action` | string | | reCAPTCHA v3 action |
| `enterprise` | bool | | reCAPTCHA Enterprise flag |
| `proxy` | string | | Proxy URL for the browser flow |

What to send per family:

| Family | Required fields |
|---|---|
| OCR / text / number / math(image) / rotate | `type` + `image_b64` or `image_url` |
| slider (+piece) | `type` + `image_b64` (+`image_b64_2`) |
| click | `type` + image + `instruction` |
| grid | use `/v1/solve/image` (tile list) |
| token (hcaptcha/recaptcha/turnstile/…) | `type` + `sitekey` + `url` |
| PoW (altcha/…) | `type` + `data: {challenge, salt, ...}` |
| math (text) | `type: math-captcha` + `data` unused, use `/v1/solve/math` or `{"type":"math-captcha"}` — see note |

> Note: `math-captcha` via `/v1/solve` needs the expression as an image;
> for raw text (`"2+3=?"`) use `POST /v1/solve/math`.

**Response** — always this shape:

```json
{ "ok": true, "type": "amazon-captcha", "ms": 231,
  "text": "AB12", "token": null, "coords": null, "selected_ids": null,
  "confidence": 0.8, "detail": { "backend": "ddddocr" } }
```

Exactly one answer field is set: `text` (OCR/math/audio), `coords`
(slider `[x]`, rotate `[angle]`, click `[x1,y1,…]` 0–1000), `selected_ids`
(grids), `token` (widgets/PoW). `detail` always carries the backend used
(`ddddocr`, `yolo`, `opencv`, `gpu-classifier`, `hash-hit`, …) plus rolling
`avg_s` / `success_rate`.

```bash
curl -X POST $API/v1/solve -H "Content-Type: application/json" \
  -d '{"type":"amazon-captcha","image_b64":"..."}'
```
```python
api.solve("amazon-captcha", image="captcha.png")["text"]
api.solve("slider-captcha", image="bg.png", image2="piece.png")["coords"]
api.token("hcaptcha", sitekey="xxx", url="https://example.com")["token"]
```
```js
(await api.solve({ type: 'amazon-captcha', image: 'captcha.png' })).text;
(await api.token('hcaptcha', 'xxx', 'https://example.com')).token;
```

Errors: `404` unknown type · `400` unreadable payload/image · `422` missing `type`.

### `POST /v1/solve/file` — solve anything (multipart upload)

Same contract, raw files instead of base64. Fields (`multipart/form-data`):

| Field | Required | Description |
|---|---|---|
| `type` | **yes** | Captcha type |
| `file` | **yes** | Main image |
| `file2` | | Slider piece |
| `instruction` | | click/grid instruction |
| `sitekey`, `url`, `langs`, `timeout` | | as above |

```bash
curl -X POST $API/v1/solve/file -F "type=amazon-captcha" -F "file=@captcha.png"
curl -X POST $API/v1/solve/file -F "type=slider-captcha" -F "file=@bg.png" -F "file2=@piece.png"
```
```python
api.solve_file("amazon-captcha", "captcha.png")
```
```js
await api.solveFile({ type: 'amazon-captcha', file: 'captcha.png' });
```

---

## Specialized endpoints

### `POST /v1/solve/image` — image grid select

```json
{ "instruction": "Select all images with traffic lights",
  "images": [{ "id": 0, "image_b64": "..." }, { "id": 1, "image_url": "https://..." }],
  "animated": false }
```
→ `{"ok":true,"selected_ids":[0,3],"detail":{"target":{...},"per_tile":{...}}}`

### `POST /v1/solve/ocr` — OCR

`{"image_b64"|"image_url", "langs":"en", "preprocess":true,
"kind":"auto|normal|text|number|russian|chinese|amazon|vk|atb|math"}` → `text`.

```bash
curl -X POST $API/v1/solve/ocr -H "Content-Type: application/json" \
  -d '{"image_b64":"...","kind":"number","langs":"en"}'
```

### `POST /v1/solve/ocr-upload` — OCR file upload

Multipart `file` (+`preprocess`). → `text`.

### `POST /v1/solve/audio` — audio transcription

Multipart `file` (wav/mp3). → `text`.

### `POST /v1/solve/slider` — slider gap

`{"bg_b64"|"bg_url", "piece_b64"|"piece_url"}` →
`{"coords":[x],"detail":{"x":x,"via":"opencv+ddddocr","track":[[dx,ms],...]}}`.
Replay `track` with a humanized drag in your bot, or let the token flow do it.

### `POST /v1/solve/rotate` — rotation angle

`{"image_b64"|"image_url"}` → `{"coords":[angle]}` (0–360).

### `POST /v1/solve/click` — click targets

`{"image_b64"|"image_url","instruction":"Click on all cats"}` →
`{"coords":[x1,y1,...],"detail":{"points":[[x,y]],"via":"grid-detector|ddddocr-det"}}`
(coordinates are 0–1000 relative).

### `POST /v1/solve/pow` — proof-of-work

`{"type":"altcha","challenge":"...","salt":"...","maxnumber":100000}` →
`{"token":"<number>"}` (submit as the PoW answer).

### `POST /v1/solve/math` — math answer

`{"text":"2+3=?"} or {"image_b64":"..."}` → `{"text":"5"}`.

---

## Token flow (hCaptcha / reCAPTCHA / Turnstile)

```bash
curl -X POST $API/v1/solve -H "Content-Type: application/json" \
  -d '{"type":"hcaptcha","sitekey":"xxx","url":"https://example.com"}'
# -> {"ok":true,"token":"P1_...","ms":12340,...}
```

Inject, then submit:

```js
// hCaptcha
document.querySelector("[name=h-captcha-response]").value = token;
// reCAPTCHA v2
document.querySelector("#g-recaptcha-response").value = token;
// Turnstile
document.querySelector("[name=cf-turnstile-response]").value = token;
// then submit the form / click the button
```

Runnable Playwright examples: `examples/hcaptcha-token-flow.py`,
`examples/hcaptcha-token-flow.js`.

---

## System endpoints

| Endpoint | Description |
|---|---|
| `GET /v1/health` | `{"ok":true,"service","version","port"}` |
| `GET /v1/capabilities` | all 39 types + method + notes |
| `GET /v1/stats` | global + per-type `avg_s`, `p50_s`, `p95_s`, `success` |
| `POST /v1/stats/reset` | reset counters |
| `GET /v1/device` | `cuda`/`mps`/`cpu`, ONNX providers, precision |
| `GET /v1/models` | model cache + background `warmup` status |
| `POST /v1/models/download` | `{"name"?}` — download + preload all |
| `GET /v1/dataset/summary` | capture bank state |
| `POST /v1/dataset/train` | `{"type","epochs","batch","lr","device","amp"}` → classifier report |
| `GET /v1/limits` | `{"api_rate_limit":"none",...}` |
| `GET /v1/openapi.json`, `GET /v1/docs.json` | machine docs |
| `GET /v1/docs` | Swagger UI |

---

## Error model

| Code | Meaning |
|---|---|
| `200` + `"ok": false` | solved attempt failed (see `detail`), safe to retry |
| `400` | unreadable image/payload |
| `404` | unknown `type` (check `/v1/capabilities`) |
| `422` | missing/invalid field (`type` required) |

There is intentionally **no 429**: concurrency is only bounded by a wide
in-memory semaphore (100) and the Playwright context pool (50).
