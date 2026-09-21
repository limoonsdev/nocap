"""FunCaptcha (Arkose): rotation / puzzle / matching, via local analysis."""
from __future__ import annotations
import time
from .base import BaseSolver, SolverContext, SolverResult

class FuncaptchaSolver(BaseSolver):
    name = "funcaptcha"
    method = "Browser + OpenCV (template match, rotation angle, similarity)"
    notes = "Common games: rotation, slider puzzle, pick-one. 100% local OpenCV."

    async def solve(self, ctx: SolverContext) -> SolverResult:
        t0 = time.time()
        try:
            from ..browser import get_driver
            async with get_driver(headless=None) as page:
                token = await page.solve_funcaptcha(ctx.url or "", ctx.sitekey or "")
                ms = int((time.time() - t0) * 1000)
                return SolverResult(ok=bool(token), token=token, confidence=0.75 if token else 0.0, ms=ms)
        except Exception as e:
            return SolverResult(ok=False, detail={"error": str(e)}, ms=int((time.time()-t0)*1000))
