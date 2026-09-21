"""Proof-of-Work / frictionless family: Altcha, Friendly, CaptchaFox, Prosopo.

Altcha/Friendly/CaptchaFox = PoW computable 100% locally (no browser needed
in most cases). Prosopo = PoW + image (PoW here, images via /solve/image).
"""
from __future__ import annotations
import time
from .base import BaseSolver, SolverContext, SolverResult
from ..ai.pow import solve_altcha, solve_pow_generic

class _PowBase(BaseSolver):
    pow_type = "altcha"
    async def solve_pow(self, challenge: str, salt: str, maxnumber: int, algorithm: str = "SHA-256") -> SolverResult:
        import time as _t
        t0 = _t.time()
        n, conf, _ = solve_altcha(challenge, salt, maxnumber, algorithm)
        ms = int((_t.time() - t0) * 1000)
        if n is None:
            return SolverResult(ok=False, confidence=0.0, detail={"error": "PoW not found (raise maxnumber)"}, ms=ms)
        return SolverResult(ok=True, token=str(n), confidence=conf,
                            detail={"number": n, "algorithm": algorithm, "type": self.pow_type}, ms=ms)
    async def solve(self, ctx: SolverContext) -> SolverResult:
        d = ctx.extra or {}
        challenge = d.get("challenge", "") or ""
        salt = d.get("salt", "") or ""
        maxn = int(d.get("maxnumber", 100000))
        algo = d.get("algorithm", "SHA-256")
        if challenge:
            return await self.solve_pow(challenge, salt, maxn, algo)
        # otherwise via browser: read the altcha fields from the page
        try:
            from ..browser import get_driver
            async with get_driver(headless=None) as page:
                await page.goto(ctx.url or "")
                tok = await page._js("return (document.querySelector('[name=altcha-response]')||{}).value || ''")
                if tok:
                    return SolverResult(ok=True, token=tok, confidence=0.9, ms=0)
        except Exception as e:
            pass
        return SolverResult(ok=False, detail={"hint": "POST /v1/solve/pow with challenge+salt"}, ms=0)

class AltchaSolver(_PowBase):
    name = "altcha"; pow_type = "altcha"
    method = "Local SHA-256 PoW (Altcha spec)"; notes = "Self-hostable, keyless, <2s."

class FriendlyCaptchaSolver(_PowBase):
    name = "friendly-captcha"; pow_type = "friendly-captcha"
    method = "Local PoW puzzle SDK"; notes = "Friendly Captcha solved locally + browser if widget."

class CaptchaFoxSolver(_PowBase):
    name = "captchafox"; pow_type = "captchafox"
    method = "PoW + local verification"; notes = "Fast CaptchaFox."

class ProsopoSolver(_PowBase):
    name = "prosopo-procaptcha"; pow_type = "prosopo-procaptcha"
    method = "PoW + image grid (via /solve/image)"; notes = "Prosopo (Polkadot): PoW here, images via image-select."
