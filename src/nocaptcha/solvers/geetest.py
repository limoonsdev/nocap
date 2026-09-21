"""GeeTest v3/v4: slider + puzzle, human trajectory via OpenCV."""
from __future__ import annotations
import time, random
from .base import BaseSolver, SolverContext, SolverResult

def human_track(distance: int) -> list[list[int]]:
    """Generate a believable human trajectory (acceleration + micro-pauses)."""
    track, cur, v = [], 0.0, 0.0
    t = 0
    mid = distance * random.uniform(0.6, 0.75)
    while cur < distance:
        a = 2.5 if cur < mid else -3.0
        v = max(0.5, v + a)
        step = v * random.uniform(0.8, 1.2)
        cur = min(distance, cur + step)
        t += random.randint(12, 35)
        track.append([int(cur), t])
    return track

class GeetestSolver(BaseSolver):
    name = "geetest"
    method = "OpenCV template-match + human trajectory"
    notes = "GeeTest v3 slider."
    async def solve(self, ctx: SolverContext) -> SolverResult:
        return SolverResult(ok=False, detail={"hint": "use the browser flow: POST /v1/solve with type geetest + url", "track_example": human_track(120)}, ms=0)

class GeetestV4Solver(BaseSolver):
    name = "geetest-v4"
    method = "OpenCV + v4 puzzle shadow analysis"
    notes = "GeeTest v4."
    async def solve(self, ctx: SolverContext) -> SolverResult:
        return SolverResult(ok=False, detail={"hint": "same as geetest v3"}, ms=0)
