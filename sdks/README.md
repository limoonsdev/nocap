# NoCaptcha SDKs — zero dependencies

Two tiny clients for the universal API (`POST /v1/solve`). No install needed,
just copy the file (or point your import at it).

| SDK | Requirements | File |
|---|---|---|
| Python | Python 3.8+, stdlib only | `sdks/python/nocaptcha_client.py` |
| Node.js | Node 18+ (`fetch`), zero deps | `sdks/nodejs/nocaptcha.js` |

## Python

```python
from nocaptcha_client import NoCaptchaClient

api = NoCaptchaClient()  # http://127.0.0.1:7888

# 1) image captcha: file path, bytes, base64 or URL
res = api.solve("amazon-captcha", image="captcha.png")
print(res["text"])          # the answer string

res = api.solve("amazon-captcha", image_url="https://.../captcha.png")
res = api.solve_file("slider-captcha", "bg.png", piece_path="piece.png")
print(res["coords"])        # [x]

# 2) browser token flow (hCaptcha / reCAPTCHA / Turnstile)
res = api.token("hcaptcha", sitekey="xxx", url="https://example.com")
print(res["token"])         # inject into [name=h-captcha-response]

# 3) shortcuts
api.ocr("captcha.png", kind="number")
api.slider("bg.png", "piece.png")
api.click("img.png", instruction="Click on all cats")
api.math(text="2+3=?")
api.health(); api.capabilities(); api.stats()
```

## Node.js

```js
const { NoCaptchaClient } = require('./sdks/nodejs/nocaptcha');
const api = new NoCaptchaClient();

const res = await api.solve({ type: 'amazon-captcha', image: 'captcha.png' });
console.log(res.text);

await api.solveFile({ type: 'slider-captcha', file: 'bg.png', file2: 'piece.png' });
const { token } = await api.token('hcaptcha', 'xxx', 'https://example.com');
```

## Response shape (all methods)

```json
{ "ok": true, "type": "amazon-captcha", "ms": 231, "text": "AB12",
  "token": null, "coords": null, "selected_ids": null,
  "confidence": 0.8, "detail": { "backend": "ddddocr" } }
```

Exactly one of `text` / `token` / `coords` / `selected_ids` carries the answer,
depending on `type`. See `docs/API.md`.
