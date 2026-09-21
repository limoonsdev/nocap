"""Browser drivers — Playwright by default (humanized mouse), Selenium as legacy.

`get_driver` dispatches on the `browser_backend` setting ("playwright" default).
Both drivers expose the same page API: goto/_js/solve_recaptcha_v2/solve_recaptcha_v3/
solve_hcaptcha/solve_turnstile/solve_funcaptcha.
"""
from __future__ import annotations
from contextlib import asynccontextmanager
from .playwright_driver import get_driver as get_driver_playwright, PlaywrightPage
from .human import human_path, human_timing

try:
    from .driver import get_driver as get_driver_selenium, SeleniumPage
except Exception:  # pragma: no cover
    get_driver_selenium = None  # type: ignore
    SeleniumPage = None  # type: ignore

try:
    from .driver import get_driver as get_driver_legacy
except Exception:  # pragma: no cover
    get_driver_legacy = None  # type: ignore

@asynccontextmanager
async def get_driver(headless: bool | None = None):
    """Yield a browser page using the configured backend (playwright default)."""
    try:
        from ..config import get_settings
        backend = (get_settings().browser_backend or "playwright").lower()
    except Exception:
        backend = "playwright"
    if backend == "selenium" and get_driver_selenium is not None:
        async with get_driver_selenium(headless=headless) as pg:
            yield pg
    else:
        async with get_driver_playwright(headless=headless) as pg:
            yield pg

__all__ = ["get_driver", "get_driver_playwright", "get_driver_selenium",
           "get_driver_legacy", "PlaywrightPage", "SeleniumPage",
           "human_path", "human_timing"]
