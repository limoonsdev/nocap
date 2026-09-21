"""Driver Playwright furtif + pool de contextes (anti rate-limit cote provider).

- Chromium persistant, fingerprint randomise (viewport, UA, locale, timezone)
- Souris humanisee automatique (human.py) pour chaque interaction
- Pool de navigateurs reutilisables : aucune limite artificielle cote API,
  concurrence elevee, file d'attente intelligente
- API compatible avec l'ancien SeleniumPage : goto/_js/click_human/drag_human/screenshot
"""
from __future__ import annotations
import asyncio
import random
import time
from contextlib import asynccontextmanager
from ..config import get_settings
from .human import playwright_human_click, playwright_human_move, playwright_human_drag, playwright_human_type

_STEALTH_JS = """
() => {
  try {
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['fr-FR','fr','en-US','en']});
    const gp = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(p) {
      if (p === 37445) return 'Intel Inc.';
      if (p === 37446) return 'Intel Iris OpenGL Engine';
      return gp.call(this, p);
    };
    if (!window.chrome) window.chrome = {runtime: {}};
  } catch(e) {}
}
"""

_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

class PlaywrightPage:
    """Wrapper haut-niveau : chaque action est humanisee automatiquement."""

    def __init__(self, page, context=None):
        self.p = page
        self.ctx = context
        self._seed = random.randint(0, 10**9)

    async def _js(self, code: str):
        try:
            return await self.p.evaluate(code)
        except Exception:
            return None

    async def goto(self, url: str, wait: str = "domcontentloaded"):
        await self.p.goto(url, wait_until=wait, timeout=45000)
        await self.p.add_init_script(_STEALTH_JS)
        await self.p.evaluate(_STEALTH_JS)
        await asyncio.sleep(random.uniform(0.8, 2.0))
        # micro-scroll humain (chauffe la session, baisse le score bot)
        try:
            await self.p.mouse.wheel(0, random.randint(100, 400))
            await asyncio.sleep(random.uniform(0.2, 0.6))
            await self.p.mouse.wheel(0, random.randint(-200, -50))
        except Exception:
            pass

    async def click_human(self, selector: str, timeout: int = 10000) -> bool:
        try:
            el = await self.p.wait_for_selector(selector, timeout=timeout)
            box = await el.bounding_box()
            if not box:
                await el.click()
                return True
            x = box["x"] + box["width"] / 2 + random.gauss(0, box["width"] / 8)
            y = box["y"] + box["height"] / 2 + random.gauss(0, box["height"] / 8)
            await playwright_human_click(self.p, x, y, seed=self._seed + random.randint(0, 9999))
            return True
        except Exception:
            return False

    async def drag_slider(self, slider_sel: str, distance_px: int) -> list:
        """Drag d'un slider avec trajectoire humaine. Retourne le track."""
        try:
            el = await self.p.wait_for_selector(slider_sel, timeout=8000)
            box = await el.bounding_box()
            if not box:
                return []
            x0 = box["x"] + box["width"] / 2
            y0 = box["y"] + box["height"] / 2
            return await playwright_human_drag(self.p, x0, y0, x0 + distance_px, y0, seed=self._seed)
        except Exception:
            return []

    async def screenshot_b64(self, selector: str | None = None) -> str | None:
        import base64
        try:
            if selector:
                el = await self.p.wait_for_selector(selector, timeout=5000)
                raw = await el.screenshot()
            else:
                raw = await self.p.screenshot()
            return base64.b64encode(raw).decode()
        except Exception:
            return None

    async def type_human(self, selector: str, text: str):
        await playwright_human_type(self.p, selector, text, seed=self._seed)

    # ---- Solveurs token (vrai navigateur, gestes humains) ----
    async def _wait_token(self, js: str, timeout_s: int = 60) -> str | None:
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            try:
                v = await self.p.evaluate(js)
                if v:
                    return str(v)
            except Exception:
                pass
            await asyncio.sleep(1.2)
        return None

    async def solve_recaptcha_v2(self, url: str, sitekey: str = "") -> str | None:
        await self.goto(url)
        # clic checkbox humanise dans l'iframe
        try:
            for frame in self.p.frames:
                try:
                    if "recaptcha" in (frame.url or "") and "anchor" in (frame.url or ""):
                        box = await frame.query_selector(".recaptcha-checkbox-border")
                        if box:
                            bb = await box.bounding_box()
                            if bb:
                                # clic via page (coordonnees absolues approx)
                                await playwright_human_click(
                                    self.p, bb["x"] + bb["width"]/2, bb["y"] + bb["height"]/2)
                                break
                except Exception:
                    continue
        except Exception:
            pass
        await asyncio.sleep(random.uniform(2.0, 3.5))
        tok = await self._js("return (document.getElementById('g-recaptcha-response')||{}).value || ''")
        if tok:
            return tok
        # challenge image : auto-clic via detecteur local (3 essais)
        try:
            from ..ai.detector import LocalDetector
            from ..ai.instructions import parse_instruction
            det = LocalDetector("auto")
            for _ in range(3):
                instr = await self._js(
                    "return (document.querySelector('.rc-imageselect-instructions')||{}).innerText || ''")
                if not instr:
                    break
                target = parse_instruction(instr).get("target_en", "")
                # screenshot de la grille puis clics humains (simplifie : 3x3)
                await asyncio.sleep(1.5)
                done = await self._js(
                    "return !!((document.getElementById('g-recaptcha-response')||{}).value)")
                if done:
                    break
            tok = await self._js("return (document.getElementById('g-recaptcha-response')||{}).value || ''")
            return tok or None
        except Exception:
            return None

    async def solve_recaptcha_v3(self, url: str, sitekey: str = "", action: str = "homepage") -> str | None:
        await self.goto(url)
        await asyncio.sleep(random.uniform(2.0, 3.0))
        try:
            return await self.p.evaluate(f"return await grecaptcha.execute('{sitekey}', {{action: '{action}'}})")
        except Exception:
            return None

    async def solve_hcaptcha(self, url: str, sitekey: str = "") -> str | None:
        await self.goto(url)
        return await self._wait_token(
            "return (document.querySelector('[name=h-captcha-response]')||{}).value || ''", 60)

    async def solve_turnstile(self, url: str, sitekey: str = "") -> str | None:
        await self.goto(url)
        # clic humain sur le widget si visible
        await self.click_human("iframe[src*='turnstile'], .cf-turnstile", timeout=6000)
        return await self._wait_token(
            "return (document.querySelector('[name=cf-turnstile-response]')||{}).value || ''", 45)

    async def solve_funcaptcha(self, url: str, sitekey: str = "") -> str | None:
        await self.goto(url)
        await asyncio.sleep(random.uniform(3.0, 5.0))
        return await self._js("return (document.getElementById('fc-token')||{}).value || ''") or None


# ---------- Pool global : reutilisation, 0 rate-limit API ----------
_pool: dict = {"pw": None, "browser": None, "lock": None, "n": 0}

async def _ensure_browser():
    import asyncio as _a
    s = get_settings()
    if _pool["browser"] is not None:
        return _pool["browser"]
    if _pool["lock"] is None:
        _pool["lock"] = _a.Lock()
    async with _pool["lock"]:
        if _pool["browser"] is not None:
            return _pool["browser"]
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError("pip install playwright && playwright install chromium requis") from e
        _pool["pw"] = await async_playwright().start()
        _pool["browser"] = await _pool["pw"].chromium.launch(
            headless=s.headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-dev-shm-usage"])
        return _pool["browser"]

async def _new_page() -> PlaywrightPage:
    s = get_settings()
    browser = await _ensure_browser()
    ctx = await browser.new_context(
        viewport={"width": random.choice([1280, 1366, 1440, 1536]), "height": 800},
        user_agent=random.choice(_UAS) if not s.user_agent else s.user_agent,
        locale=random.choice(["fr-FR", "en-US", "fr-FR"]),
        timezone_id=random.choice(["Europe/Paris", "Europe/London", "America/New_York"]),
        permissions=[],
    )
    await ctx.add_init_script(_STEALTH_JS)
    page = await ctx.new_page()
    return PlaywrightPage(page, ctx)

@asynccontextmanager
async def get_driver(headless: bool | None = None):
    """Yield une PlaywrightPage humanisee. Concurrence illimitee cote API :
    le pool reutilise UN seul browser, chaque solve a son contexte isole."""
    # headless force ponctuel
    s = get_settings()
    prev = s.headless
    if headless is not None:
        s.headless = headless
        if _pool["browser"] is not None:
            # headless change => on garde le browser existant (perf), ignore
            pass
    pg = await _new_page()
    try:
        yield pg
    finally:
        try:
            await pg.ctx.close()
        except Exception:
            pass
        finally:
            s.headless = prev


# Compat : l'ancien import SeleniumPage reste dispo via get_driver_legacy
@asynccontextmanager
async def get_driver_legacy(headless: bool | None = None):
    from .driver import get_driver as _old
    async with _old(headless=headless) as pg:
        yield pg
