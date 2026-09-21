"""reCAPTCHA v2: checkbox + image/audio challenge solved locally via a real browser."""
from __future__ import annotations
import time
from .base import BaseSolver, SolverContext, SolverResult

class RecaptchaV2Solver(BaseSolver):
    name = "recaptcha-v2"
    method = "Playwright + local AI (checkbox click, 3x3/4x4 grid reading, audio fallback)"
    notes = "No bypass: real browser, human gestures, local visual solving."

    async def solve(self, ctx: SolverContext) -> SolverResult:
        t0 = time.time()
        try:
            from ..browser import get_driver
            async with get_driver(headless=None) as page:
                token = await page.solve_recaptcha_v2(ctx.url or "", ctx.sitekey or "")
                ms = int((time.time() - t0) * 1000)
                if token:
                    return SolverResult(ok=True, token=token, confidence=0.9, detail={"via": "browser+local-ai"}, ms=ms)
                return SolverResult(ok=False, detail={"error": "challenge not solved (timeout or network block)"}, ms=ms)
        except Exception as e:
            return SolverResult(ok=False, detail={"error": f"{type(e).__name__}: {e}", "hint": "run `nocaptcha doctor` to check the browser"}, ms=int((time.time()-t0)*1000))
