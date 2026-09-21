"""hCaptcha: image / text / animated grid, solved 100% locally."""
from __future__ import annotations
import time
from .base import BaseSolver, SolverContext, SolverResult

class HcaptchaSolver(BaseSolver):
    name = "hcaptcha"
    method = "Playwright + LocalDetector + OCR + animated vote"
    notes = "Handles FR/EN instructions ('select all...', 'selectionnez...'), 3x3 tiles, animated images."

    async def solve(self, ctx: SolverContext) -> SolverResult:
        t0 = time.time()
        try:
            from ..browser import get_driver
            async with get_driver(headless=None) as page:
                token = await page.solve_hcaptcha(ctx.url or "", ctx.sitekey or "")
                ms = int((time.time() - t0) * 1000)
                if token:
                    return SolverResult(ok=True, token=token, confidence=0.88, detail={"via": "browser+local-ai"}, ms=ms)
                return SolverResult(ok=False, detail={"error": "hCaptcha not solved"}, ms=ms)
        except Exception as e:
            return SolverResult(ok=False, detail={"error": str(e)}, ms=int((time.time()-t0)*1000))
