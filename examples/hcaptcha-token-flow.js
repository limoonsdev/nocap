/**
 * Generic token-injection flow (Playwright + NoCaptcha API).
 *
 *  1. your bot fills the form (username, email, password, ...),
 *  2. NoCaptcha solves the captcha in a stealth browser and returns a token,
 *  3. this script injects the token into the page and submits.
 *
 * Usage:
 *   npm i playwright && npx playwright install chromium
 *   node examples/hcaptcha-token-flow.js --url https://example.com/register \
 *     --provider hcaptcha --sitekey YOUR_SITEKEY
 *
 * IMPORTANT: only automate sites you own or that explicitly allow it.
 * Automated account creation may violate a site's Terms of Service.
 */
'use strict';

const { chromium } = require('playwright');
const { NoCaptchaClient } = require('../sdks/nodejs/nocaptcha');

const PROVIDERS = {
  'hcaptcha': "[name='h-captcha-response']",
  'recaptcha-v2': '#g-recaptcha-response',
  'turnstile': "[name='cf-turnstile-response']",
};

function arg(name, def = '') {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}

(async () => {
  const url = arg('--url');
  const provider = arg('--provider', 'hcaptcha');
  const apiBase = arg('--api', 'http://127.0.0.1:7888');
  const submit = arg('--submit', '');
  const headless = process.argv.includes('--headless');
  if (!url || !PROVIDERS[provider]) {
    console.error('Usage: node hcaptcha-token-flow.js --url <page> [--provider hcaptcha|recaptcha-v2|turnstile] [--sitekey xxx] [--submit <selector>] [--headless]');
    process.exit(2);
  }
  const selector = PROVIDERS[provider];
  const api = new NoCaptchaClient(apiBase);
  console.log('[+] NoCaptcha API:', await api.health());

  const browser = await chromium.launch({ headless });
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  console.log('[+] page loaded:', url);

  let sitekey = arg('--sitekey', '');
  if (!sitekey) {
    sitekey = await page.evaluate(() => {
      const el = document.querySelector(
        "iframe[src*='hcaptcha'], iframe[src*='recaptcha'], iframe[src*='turnstile'], [data-sitekey]");
      if (!el) return '';
      return el.dataset.sitekey
        || new URL(el.src || '', location.href).searchParams.get('sitekey')
        || '';
    });
  }
  if (!sitekey) { console.error('[-] sitekey not found (pass --sitekey)'); process.exit(2); }
  console.log('[+] sitekey:', sitekey);

  // TODO: fill your form fields here, e.g.
  // await page.fill('#username', '...');

  console.log('[\\] asking NoCaptcha for a token...');
  const res = await api.token(provider, sitekey, url);
  if (!res.ok || !res.token) { console.error('[-] solve failed:', res); process.exit(1); }
  console.log(`[+] token received in ${res.ms}ms (conf ${res.confidence})`);

  const status = await page.evaluate(([sel, token]) => {
    const el = document.querySelector(sel);
    if (!el) return 'field-not-found';
    el.value = token;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return 'injected';
  }, [selector, res.token]);
  console.log('[+] injection:', status);
  if (submit) { await page.click(submit); console.log('[+] submit clicked'); }
  else { console.log('[\\] no --submit given: call your form submit here'); }
  await page.waitForTimeout(4000);
  await browser.close();
})().catch((e) => { console.error('[-]', e.message); process.exit(1); });
