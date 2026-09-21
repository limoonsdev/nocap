"""NoCap server: API-only FastAPI app at http://localhost:7888/ + /v1/... (0 rate-limit).

On boot: background warmup downloads + preloads all optimal resources
(ONNX zoo, ddddocr, rapidocr, YOLO). The API answers immediately;
live status at GET /v1/models (warmup field).
"""
from __future__ import annotations
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes_health import router as health_router
from .api.routes_solve import router as solve_router
from .api.routes_stats import router as stats_router
from . import __version__
from .log import banner, ok, info as log_info

@asynccontextmanager
async def lifespan(app: FastAPI):
    from . import resources
    started = resources.warmup_background()
    if started:
        ok("background warmup started: ONNX + ddddocr + rapidocr + yolo")
    else:
        log_info("warmup already running")
    yield

def create_app() -> FastAPI:
    app = FastAPI(
        title="NoCaptcha API",
        version=__version__,
        description="100% local captcha solver (humanized Playwright): 35+ types, speed metrics, auto-learn, 0 rate-limit.",
        docs_url="/v1/docs",
        redoc_url="/v1/redoc",
        openapi_url="/v1/openapi.json",
        lifespan=lifespan,
    )
    # 0 rate-limit: open CORS, no throttle middleware
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(health_router, prefix="/v1")
    app.include_router(solve_router, prefix="/v1")
    app.include_router(stats_router, prefix="/v1")

    @app.get("/v1/docs.json", summary="Full API documentation (OpenAPI JSON)")
    async def docs_json():
        return app.openapi()

    @app.get("/", include_in_schema=False)
    async def root():
        return {"service": "nocaptcha", "version": __version__,
                "docs": "/v1/docs", "openapi": "/v1/openapi.json",
                "stats": "/v1/stats", "rate_limit": "none"}
    return app

app = create_app()

def run(host: str = "127.0.0.1", port: int = 7888, log_level: str = "info"):
    import uvicorn
    banner()
    ok(f"NoCaptcha v{__version__} starting")
    log_info(f"API docs : http://{host}:{port}/v1/docs")
    log_info(f"OpenAPI  : http://{host}:{port}/v1/openapi.json")
    uvicorn.run("nocaptcha.server:app", host=host, port=port, log_level=log_level)

def export_openapi(path: str = "docs/API.json"):
    import pathlib
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False), encoding="utf-8")
    return str(p)
