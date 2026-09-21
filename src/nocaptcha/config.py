"""Global NoCaptcha settings (env + file)."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOCAPTCHA_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 7888
    log_level: str = "info"

    # Local AI
    models_dir: Path = Path("./models")
    detector_backend: str = "auto"  # auto | yolo | clip | heuristic
    ocr_backend: str = "auto"  # auto | rapidocr | easyocr | tesseract
    ocr_langs: str = "fr,en"
    max_workers: int = 4
    solve_timeout: int = 90

    # Browser — stealth Playwright by default
    browser_backend: str = "playwright"  # playwright | selenium
    headless: bool = True
    chrome_path: str = ""
    user_agent: str = ""
    pool_max_contexts: int = 50  # browser concurrency (0 API rate-limit)
    human_mouse: bool = True

    # Anti rate-limit / perf (no artificial API limit)
    api_rate_limit: str = "none"  # none = max throughput
    max_concurrent_solves: int = 100

    # Auto-learning
    learn_enabled: bool = True
    learn_dir: Path = Path("./models/captures")

    # Device: GPU when available, else CPU (auto | cuda | mps | cpu)
    device: str = "auto"
    train_epochs: int = 10
    train_batch: int = 64
    train_lr: float = 3e-3
    train_amp: bool = True  # fp16 on CUDA: faster, accuracy kept

    # API
    api_token: str = ""  # empty = no local auth

@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.models_dir.mkdir(parents=True, exist_ok=True)
    return s
