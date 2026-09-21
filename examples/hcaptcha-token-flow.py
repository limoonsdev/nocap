"""Generic token-injection flow (Playwright + NoCaptcha API).

Works with any site embedding hCaptcha / reCAPTCHA v2 / Turnstile:
  1. your bot fills the form (username, email, password, ...),
  2. NoCaptcha solves the captcha in a stealth browser and returns a token,
  3. this script injects the token into the page and submits.

Usage:
    pip install playwright && playwright install chromium
    python examples/hcaptcha-token-flow.py --url https://example.com/register \\
        --provider hcaptcha --sitekey YOUR_SITEKEY

IMPORTANT: only automate sites you own or that explicitly allow it.
Automated account creation may violate a site's Terms of Service.
"""
from __future__ import annotations
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdks", "python"))
from nocaptcha_client import NoCaptchaClient  # noqa: E402

# provider -> (textarea selector, extra submit hint)
PROVIDERS = {
    "hcaptcha": ("[name='h-captcha-response']", "hCaptcha"),
    "recaptcha-v2": ("#g-recaptcha-response", "reCAPTCHA v2"),
    "turnstile": ("[name='cf-turnstile-response']", "Turnstile"),
}

INJECT_JS = """(args) => {
  const [selector, token] = args;
  const el = document.querySelector(selector);
  if (!el) return 'field-not-found';
  el.value = token;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return 'injected';
}"""


def main() -> int:
    ap = argparse.ArgumentParser(description="NoCaptcha token-injection flow")
    ap.add_argument("--url", required=True, help="Registration page URL")
    ap.add_argument("--provider", default="hcaptcha", choices=list(PROVIDERS),
                    help="Captcha provider on the page")
    ap.add_argument("--sitekey", default="", help="Widget sitekey (auto-detected if empty)")
    ap.add_argument("--api", default="http://127.0.0.1:7888", help="NoCaptcha base URL")
    ap.add_argument("--submit", default="", help="Optional CSS selector of the submit button to click")
    ap.add_argument("--headless", action="store_true", help="Run the browser headless")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    selector, label = PROVIDERS[args.provider]
    api = NoCaptchaClient(args.api)
    print(f"[+] NoCaptcha API: {api.health()}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()
        page.goto(args.url, wait_until="domcontentloaded")
        print(f"[+] page loaded: {args.url}")

        sitekey = args.sitekey
        if not sitekey:
            # auto-detect the widget sitekey from the DOM
            sitekey = page.eval_on_selector(
                "iframe[src*='hcaptcha'], iframe[src*='recaptcha'], iframe[src*='turnstile'], "
                "[data-sitekey]",
                """el => el.dataset.sitekey
                   || new URL(el.src || '', location.href).searchParams.get('sitekey')
                   || ''""",
            ) or ""
        if not sitekey:
            print("[-] sitekey not found (pass --sitekey explicitly)")
            return 2
        print(f"[+] {label} sitekey: {sitekey}")

        # TODO: fill your form fields here, e.g.
        # page.fill("#username", "...")
        # page.fill("#email", "...")

        print("[\\] asking NoCaptcha for a token...")
        res = api.token(args.provider, sitekey, args.url)
        if not res.get("ok") or not res.get("token"):
            print(f"[-] solve failed: {res}")
            return 1
        token = res["token"]
        print(f"[+] token received in {res.get('ms')}ms (conf {res.get('confidence')})")

        status = page.evaluate(INJECT_JS, [selector, token])
        print(f"[+] injection: {status}")
        if args.submit:
            page.click(args.submit)
            print("[+] submit clicked")
        else:
            print("[\\] no --submit given: call your form submit here")
        page.wait_for_timeout(4000)
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
