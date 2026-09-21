"""Pydantic v1 API schemas — the JSON docs are generated from these models."""
from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field

class CaptchaType(str, Enum):
    # Google / Cloudflare / classic
    recaptcha_v2 = "recaptcha-v2"
    recaptcha_v3 = "recaptcha-v3"
    recaptcha_enterprise = "recaptcha-enterprise"
    hcaptcha = "hcaptcha"
    turnstile = "turnstile"
    funcaptcha = "funcaptcha"
    arkose = "arkose"
    geetest = "geetest"
    geetest_v4 = "geetest-v4"
    # Image / text / audio
    image_select = "image-select"
    image_captcha = "image-captcha"
    image_text = "image-text"
    normal_captcha = "normal-captcha"
    text_captcha = "text-captcha"
    number_captcha = "number-captcha"
    russian_captcha = "russian-captcha"
    chinese_captcha = "chinese-captcha"
    amazon_captcha = "amazon-captcha"
    vk_captcha = "vk-captcha"
    atb_captcha = "atb-captcha"
    math_captcha = "math-captcha"
    click_captcha = "click-captcha"
    audio = "audio"
    audio_captcha = "audio-captcha"
    # Puzzle / slider / rotate
    slider_captcha = "slider-captcha"
    rotate_captcha = "rotate-captcha"
    cutcaptcha = "cutcaptcha"
    capy_puzzle = "capy-puzzle"
    temu_captcha = "temu-captcha"
    lemin_captcha = "lemin-captcha"
    binance_captcha = "binance-captcha"
    tencent_captcha = "tencent-captcha"
    # PoW / frictionless
    altcha = "altcha"
    friendly_captcha = "friendly-captcha"
    captchafox = "captchafox"
    mtcaptcha = "mtcaptcha"
    prosopo = "prosopo-procaptcha"
    # Bot-protection / enterprise
    datadome = "datadome-captcha"
    imperva = "imperva-captcha"

class SolveRequest(BaseModel):
    type: CaptchaType = Field(..., description="Captcha type to solve (35+ supported, see /v1/capabilities)")
    sitekey: Optional[str] = Field(None, description="Sitekey (reCAPTCHA/hCaptcha/Turnstile/Funcaptcha/MTCaptcha...)")
    url: Optional[str] = Field(None, description="Page URL hosting the captcha (browser token flow)")
    enterprise: bool = False
    action: Optional[str] = Field(None, description="reCAPTCHA v3 action")
    proxy: Optional[str] = Field(None, description="Optional proxy URL for the browser flow")
    timeout: int = Field(90, ge=5, le=600)
    # Universal payload — solve anything through a single endpoint
    image_b64: Optional[str] = Field(None, description="Main image as base64 (OCR / slider bg / rotate / click)")
    image_b64_2: Optional[str] = Field(None, description="Second image as base64 (slider piece)")
    image_url: Optional[str] = Field(None, description="Main image URL (fetched server-side, no CORS issues)")
    instruction: Optional[str] = Field(None, description="Instruction (image-select / click / lemin)")
    langs: str = Field("fr,en", description="OCR languages: fr,en,ru,zh")
    data: dict[str, Any] = Field(default_factory=dict, description="Vendor payload (altcha challenge/salt, tencent appid...)")

    model_config = {"json_schema_extra": {"example": {"type": "hcaptcha", "sitekey": "xxx", "url": "https://example.com"}}}

class ImageTile(BaseModel):
    id: int | str
    image_b64: Optional[str] = None
    image_url: Optional[str] = None

class ImageSolveRequest(BaseModel):
    instruction: str = Field(..., description="E.g. 'Select all images with traffic lights'")
    images: list[ImageTile]
    animated: bool = Field(False, description="True for animated tiles (gif/webp/video)")

class OcrRequest(BaseModel):
    image_b64: Optional[str] = None
    image_url: Optional[str] = None
    langs: str = "fr,en"
    preprocess: bool = True
    kind: str = Field("auto", description="auto|normal|text|number|russian|chinese|amazon|vk|atb|math")

class SliderRequest(BaseModel):
    bg_b64: Optional[str] = None
    bg_url: Optional[str] = None
    piece_b64: Optional[str] = None
    piece_url: Optional[str] = None
    width: int = 300

class RotateRequest(BaseModel):
    image_b64: Optional[str] = None
    image_url: Optional[str] = None

class ClickRequest(BaseModel):
    image_b64: Optional[str] = None
    image_url: Optional[str] = None
    instruction: str = Field(..., description="E.g. 'Click on all cats'")

class PowRequest(BaseModel):
    type: str = Field("altcha", description="altcha|friendly-captcha|captchafox|prosopo-procaptcha")
    challenge: str = ""
    salt: str = ""
    maxnumber: int = 100000
    algorithm: str = "SHA-256"
    data: dict[str, Any] = {}

class MathRequest(BaseModel):
    image_b64: Optional[str] = None
    image_url: Optional[str] = None
    text: Optional[str] = Field(None, description="If already OCRed: '2 + 3 = ?'")

class TrainRequest(BaseModel):
    type: Optional[str] = Field(None, description="Type to train (empty = global bank)")
    epochs: int = Field(10, ge=1, le=100)
    batch: int = Field(64, ge=4, le=512)
    lr: float = Field(3e-3, ge=1e-5, le=1e-1)
    device: str = Field("auto", description="auto|cuda|mps|cpu (GPU when available)")
    amp: bool = Field(True, description="AMP fp16 on CUDA")

class SolveResponse(BaseModel):
    ok: bool
    type: str
    ms: int
    token: Optional[str] = Field(None, description="Solution token (g-recaptcha-response, h-captcha-response...)")
    coords: Optional[list[int]] = None
    selected_ids: Optional[list[Any]] = None
    text: Optional[str] = None
    confidence: float = 0.0
    detail: dict[str, Any] = {}

class Capability(BaseModel):
    type: str
    supported: bool
    method: str
    local: bool = True
    notes: str = ""
