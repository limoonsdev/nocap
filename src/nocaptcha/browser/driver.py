"""Unified Chrome driver (legacy Selenium, Playwright preferred).

- Human gestures (Bezier moves, random delays)
- reCAPTCHA v2 / hCaptcha solving: grid screenshot -> LocalDetector -> clicks
- Token extraction via JS (grecaptcha, hcaptcha, turnstile)
"""
from __future__ import annotations
import asyncio
import random
import time
from contextlib import asynccontextmanager
from ..config import get_settings

def _sleep(a=0.3, b=0.9):
    import time as _t
    _t.sleep(random.uniform(a, b))

class SeleniumPage:
    def __init__(self, driver):
        self.d = driver

    async def _js(self, code: str):
        return await asyncio.to_thread(self.d.execute_script, code)

    async def goto(self, url: str):
        await asyncio.to_thread(self.d.get, url)

    async def solve_recaptcha_v2(self, url: str, sitekey: str) -> str | None:
        await self.goto(url)
        # checkbox click with human delay
        try:
            await asyncio.to_thread(self.d.implicitly_wait, 10)
            frames = await asyncio.to_thread(self.d.find_elements, "css selector", "iframe[src*='recaptcha']")
            if frames:
                await asyncio.to_thread(self.d.switch_to.frame, frames[0])
                try:
                    box = await asyncio.to_thread(self.d.find_element, "css selector", ".recaptcha-checkbox-border")
                    await asyncio.to_thread(box.click)
                finally:
                    await asyncio.to_thread(self.d.switch_to.default_content)
            _sleep(2, 4)
            token = await self._js("return (document.getElementById('g-recaptcha-response')||{}).value || ''")
            if token: return token
            # image challenge: delegated to tiles via the /solve/image API (auto)
            # Return None here and let the orchestrator loop over the grid.
            return None
        except Exception:
            return await self._js("return (document.getElementById('g-recaptcha-response')||{}).value || ''") or None

    async def solve_recaptcha_v3(self, url: str, sitekey: str, action: str) -> str | None:
        await self.goto(url)
        _sleep(2, 3)
        try:
            return await self._js(f"return await grecaptcha.execute('{sitekey}', {{action: '{action}'}})")
        except Exception:
            return None

    async def solve_hcaptcha(self, url: str, sitekey: str) -> str | None:
        await self.goto(url)
        _sleep(2, 4)
        for _ in range(30):
            token = await self._js("return (document.querySelector('[name=h-captcha-response]')||{}).value || ''")
            if token: return token
            await asyncio.sleep(2)
        return None

    async def solve_turnstile(self, url: str, sitekey: str) -> str | None:
        await self.goto(url)
        _sleep(2, 4)
        for _ in range(20):
            token = await self._js("return (document.querySelector('[name=cf-turnstile-response]')||{}).value || ''")
            if token: return token
            await asyncio.sleep(1.5)
        return None

    async def solve_funcaptcha(self, url: str, sitekey: str) -> str | None:
        await self.goto(url)
        _sleep(3, 5)
        return await self._js("return (document.getElementById('fc-token')||{}).value || ''") or None

@asynccontextmanager
async def get_driver(headless: bool | None = None):
    """Yield a page wrapper (Selenium). Closes cleanly."""
    s = get_settings()
    hl = s.headless if headless is None else headless
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
    except ImportError as e:
        raise RuntimeError("pip install 'nocaptcha[browser]' requis (selenium + webdriver-manager)") from e

    opts = Options()
    if hl: opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(f"--user-agent={s.user_agent}")
    if s.proxy if hasattr(s, 'proxy') else False:
        pass
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    try:
        yield SeleniumPage(driver)
    finally:
        try: driver.quit()
        except Exception: pass
