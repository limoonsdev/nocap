"""Souris humanisee : courbes de Bezier, loi de Fitts, jitter, micro-pauses.

Utilise par le driver Playwright pour chaque clic / drag / typing.
100% local, 0 dependance. Reproductible via seed optionnel.
"""
from __future__ import annotations
import asyncio
import math
import random


def _bezier(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    u = 1 - t
    x = u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0]
    y = u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]
    return x, y


def human_path(x0: float, y0: float, x1: float, y1: float,
               seed: int | None = None, steps: int | None = None) -> list[tuple[float, float]]:
    """Trajectoire souris humaine : Bezier cubique + bruit + vitesse Fitts."""
    rnd = random.Random(seed)
    dist = math.hypot(x1 - x0, y1 - y0)
    if dist < 2:
        return [(x1, y1)]
    # points de controle avec deviation perpendiculaire aleatoire
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    nx, ny = -dy / (dist + 1e-9), dx / (dist + 1e-9)
    off1 = rnd.uniform(-dist * 0.15, dist * 0.15)
    off2 = rnd.uniform(-dist * 0.15, dist * 0.15)
    t = rnd.uniform(0.25, 0.4)
    p1 = (x0 + dx * t + nx * off1, y0 + dy * t + ny * off1)
    p2 = (x0 + dx * (1 - t) + nx * off2, y0 + dy * (1 - t) + ny * off2)
    # loi de Fitts : temps ~= a + b*log2(D/W + 1), steps proportionnels
    n = steps or max(12, min(60, int(12 + dist / 18)))
    pts: list[tuple[float, float]] = []
    for i in range(1, n + 1):
        # easing ease-in-out (lent au debut/fin comme un humain)
        tt = i / n
        ease = tt * tt * (3 - 2 * tt)
        x, y = _bezier((x0, y0), p1, p2, (x1, y1), ease)
        x += rnd.gauss(0, 1.2)
        y += rnd.gauss(0, 1.2)
        pts.append((x, y))
    pts.append((x1 + rnd.gauss(0, 0.6), y1 + rnd.gauss(0, 0.6)))
    return pts


def human_timing(dist: float, seed: int | None = None) -> float:
    """Duree totale (s) d'un mouvement selon Fitts + jitter."""
    rnd = random.Random(seed)
    base = 0.18 + 0.09 * math.log2(dist / 8 + 1)
    return max(0.12, rnd.gauss(base, base * 0.18))


async def playwright_human_move(page, x0: float, y0: float, x1: float, y1: float,
                                seed: int | None = None):
    """Deplace la souris Playwright le long d'un chemin humain."""
    pts = human_path(x0, y0, x1, y1, seed=seed)
    total = human_timing(math.hypot(x1 - x0, y1 - y0), seed=seed)
    per = total / max(1, len(pts))
    for x, y in pts:
        try:
            await page.mouse.move(x, y)
        except Exception:
            break
        await asyncio.sleep(per * random.uniform(0.7, 1.3))


async def playwright_human_click(page, x: float, y: float, seed: int | None = None):
    """Move humain + micro-pause + down/up avec jitter (anti-detect)."""
    rnd = random.Random(seed)
    try:
        pos = await page.evaluate("() => ({x: 0, y: 0})")
    except Exception:
        pos = {"x": 0, "y": 0}
    # position courante inconnue -> on part d'un point proche aleatoire
    sx = x + rnd.uniform(-120, -40)
    sy = y + rnd.uniform(-80, 80)
    await playwright_human_move(page, sx, sy, x, y, seed=seed)
    await asyncio.sleep(rnd.uniform(0.05, 0.22))
    try:
        await page.mouse.move(x + rnd.gauss(0, 1.0), y + rnd.gauss(0, 1.0))
        await page.mouse.down()
        await asyncio.sleep(rnd.uniform(0.04, 0.14))
        await page.mouse.up()
    except Exception:
        try:
            await page.mouse.click(x, y)
        except Exception:
            pass
    await asyncio.sleep(rnd.uniform(0.08, 0.3))


async def playwright_human_drag(page, x0: float, y0: float, x1: float, y1: float,
                                seed: int | None = None) -> list[list[int]]:
    """Drag slider humain : deplacement Bezier + track temps reel retourne."""
    import time
    rnd = random.Random(seed)
    await playwright_human_move(page, x0 - rnd.uniform(30, 80), y0 + rnd.uniform(-30, 30), x0, y0, seed=seed)
    await asyncio.sleep(rnd.uniform(0.08, 0.25))
    pts = human_path(x0, y0, x1, y1, seed=seed)
    track: list[list[int]] = []
    t0 = time.time()
    try:
        await page.mouse.move(x0, y0)
        await page.mouse.down()
        for x, y in pts:
            await page.mouse.move(x, y)
            await asyncio.sleep(rnd.uniform(0.008, 0.025))
            track.append([int(x - x0), int((time.time() - t0) * 1000)])
        await page.mouse.up()
    except Exception:
        try:
            await page.mouse.up()
        except Exception:
            pass
    # overshoot humain occasionnel
    if rnd.random() < 0.5 and track:
        track.append([int(x1 - x0) + rnd.randint(2, 6), track[-1][1] + rnd.randint(40, 90)])
        track.append([int(x1 - x0), track[-1][1] + rnd.randint(60, 140)])
    return track


async def playwright_human_type(page, selector: str, text: str, seed: int | None = None):
    """Frappe clavier humaine : delais variables, fautes corrigees rares."""
    rnd = random.Random(seed)
    try:
        await page.click(selector)
    except Exception:
        pass
    await asyncio.sleep(rnd.uniform(0.1, 0.3))
    for ch in text:
        try:
            await page.keyboard.type(ch)
        except Exception:
            break
        await asyncio.sleep(rnd.uniform(0.03, 0.14))
        if rnd.random() < 0.008:  # micro-hesitation
            await asyncio.sleep(rnd.uniform(0.2, 0.5))
