# NoCaptcha examples

> Only automate sites you own or that explicitly allow it. Automated account
> creation may violate a site's Terms of Service.

## Token-injection flow (account-creator pattern)

The standard way to plug NoCaptcha into any bot (account creator, checker,
form filler) for hCaptcha / reCAPTCHA v2 / Turnstile:

1. Your bot fills the form fields.
2. It reads the widget `sitekey` from the page.
3. It calls the universal API: `POST /v1/solve {"type","sitekey","url"}`.
4. NoCaptcha solves it in a stealth browser and returns `{"token": ...}`.
5. Your bot injects the token into the page field and submits.

| File | Stack |
|---|---|
| `examples/hcaptcha-token-flow.py` | Python + Playwright + stdlib SDK |
| `examples/hcaptcha-token-flow.js` | Node.js + Playwright + fetch SDK |

```bash
pip install playwright && playwright install chromium
python examples/hcaptcha-token-flow.py --url https://example.com/register \
    --provider hcaptcha --sitekey YOUR_SITEKEY --submit "#register-btn"
```

Provider field map used for injection:

| Provider | `type` | Token field | Notes |
|---|---|---|---|
| hCaptcha | `hcaptcha` | `[name=h-captcha-response]` | then submit the form |
| reCAPTCHA v2 | `recaptcha-v2` | `#g-recaptcha-response` | then submit the form |
| Turnstile | `turnstile` | `[name=cf-turnstile-response]` | then submit the form |

## Direct API (curl)

```bash
# image captcha: base64
curl -X POST http://127.0.0.1:7888/v1/solve \
  -H "Content-Type: application/json" \
  -d '{"type":"amazon-captcha","image_b64":"..."}'

# image captcha: raw file upload (no base64 needed)
curl -X POST http://127.0.0.1:7888/v1/solve/file \
  -F "type=amazon-captcha" -F "file=@captcha.png"

# image captcha: remote URL (fetched server-side)
curl -X POST http://127.0.0.1:7888/v1/solve \
  -H "Content-Type: application/json" \
  -d '{"type":"amazon-captcha","image_url":"https://.../captcha.png"}'

# browser token flow
curl -X POST http://127.0.0.1:7888/v1/solve \
  -H "Content-Type: application/json" \
  -d '{"type":"hcaptcha","sitekey":"xxx","url":"https://example.com"}'
```
