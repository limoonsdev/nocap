"""Cloudflare Turnstile: non-interactive checkbox — a real browser is enough."""
from __future__ import annotations
import time
from .base import BaseSolver, SolverContext, SolverResult

class TurnstileSolver(BaseSolver):
    name = "turnstile"
    method = "Real browser, waits for the cf-turnstile-response token"
    notes = "No AI needed in 95% of cases; human retry on interactive challenge."

    async def solve(self, ctx: SolverContext) -> SolverResult:
        t0 = time.time()
        try:
            from ..browser import get_driver
            async with get_driver(headless=None) as page:
                token = await page.solve_turnstile(ctx.url or "", ctx.sitekey or "")
                ms = int((time.time() - t0) * 1000)
                return SolverResult(ok=bool(token), token=token, confidence=0.9 if token else 0.0, ms=ms)
        except Exception as e:
            return SolverResult(ok=False, detail={"error": str(e)}, ms=int((time.time()-t0)*1000))
