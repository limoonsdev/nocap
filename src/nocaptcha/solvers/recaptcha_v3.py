"""reCAPTCHA v3 / Enterprise: risk-based score — orchestrated in a real browser."""
from __future__ import annotations
import time
from .base import BaseSolver, SolverContext, SolverResult

class RecaptchaV3Solver(BaseSolver):
    name = "recaptcha-v3"
    method = "Real browser + action wait + grecaptcha.execute extraction"
    notes = "v3 is not solved visually: we run the legitimate JS in Chromium and return the token."

    async def solve(self, ctx: SolverContext) -> SolverResult:
        t0 = time.time()
        try:
            from ..browser import get_driver
            async with get_driver(headless=None) as page:
                token = await page.solve_recaptcha_v3(ctx.url or "", ctx.sitekey or "", ctx.action or "homepage")
                ms = int((time.time() - t0) * 1000)
                return SolverResult(ok=bool(token), token=token, confidence=0.8 if token else 0.0,
                                    detail={"action": ctx.action or "homepage"}, ms=ms)
        except Exception as e:
            return SolverResult(ok=False, detail={"error": str(e)}, ms=int((time.time()-t0)*1000))
