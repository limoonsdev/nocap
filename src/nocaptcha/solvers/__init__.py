"""Init solvers — 35+ types."""
from .base import BaseSolver, SolverContext, SolverResult
from .recaptcha_v2 import RecaptchaV2Solver
from .hcaptcha import HcaptchaSolver
from .turnstile import TurnstileSolver
from .recaptcha_v3 import RecaptchaV3Solver
from .funcaptcha import FuncaptchaSolver
from .geetest import GeetestSolver, GeetestV4Solver
from .image_text import ImageSelectSolver, ImageTextSolver
from .audio import AudioSolver
from .text_captcha import (
    NormalCaptchaSolver, TextCaptchaSolver, NumberCaptchaSolver,
    RussianCaptchaSolver, ChineseCaptchaSolver, AmazonCaptchaSolver,
    VkCaptchaSolver, AtbCaptchaSolver, MathCaptchaSolver,
)
from .pow_captcha import AltchaSolver, FriendlyCaptchaSolver, CaptchaFoxSolver, ProsopoSolver
from .puzzle import (
    SliderCaptchaSolver, RotateCaptchaSolver, ClickCaptchaSolver,
    CutcaptchaSolver, CapyPuzzleSolver, TemuCaptchaSolver, LeminCaptchaSolver,
    BinanceCaptchaSolver, TencentCaptchaSolver, MTCaptchaSolver,
    DataDomeSolver, ImpervaSolver, ArkoseSolver,
)

_recaptcha_enterprise = RecaptchaV3Solver()
_recaptcha_enterprise.name = "recaptcha-enterprise"

_image_captcha = ImageSelectSolver()
_image_captcha.name = "image-captcha"

_audio_alias = AudioSolver()
_audio_alias.name = "audio-captcha"

REGISTRY: dict[str, BaseSolver] = {
    # Google / Cloudflare / classiques
    "recaptcha-v2": RecaptchaV2Solver(),
    "recaptcha-v3": RecaptchaV3Solver(),
    "recaptcha-enterprise": _recaptcha_enterprise,
    "hcaptcha": HcaptchaSolver(),
    "turnstile": TurnstileSolver(),
    "funcaptcha": FuncaptchaSolver(),
    "arkose": ArkoseSolver(),
    "geetest": GeetestSolver(),
    "geetest-v4": GeetestV4Solver(),
    # Image / texte / audio
    "image-select": ImageSelectSolver(),
    "image-captcha": _image_captcha,
    "image-text": ImageTextSolver(),
    "normal-captcha": NormalCaptchaSolver(),
    "text-captcha": TextCaptchaSolver(),
    "number-captcha": NumberCaptchaSolver(),
    "russian-captcha": RussianCaptchaSolver(),
    "chinese-captcha": ChineseCaptchaSolver(),
    "amazon-captcha": AmazonCaptchaSolver(),
    "vk-captcha": VkCaptchaSolver(),
    "atb-captcha": AtbCaptchaSolver(),
    "math-captcha": MathCaptchaSolver(),
    "click-captcha": ClickCaptchaSolver(),
    "audio": AudioSolver(),
    "audio-captcha": _audio_alias,
    # Puzzle / slider / rotate
    "slider-captcha": SliderCaptchaSolver(),
    "rotate-captcha": RotateCaptchaSolver(),
    "cutcaptcha": CutcaptchaSolver(),
    "capy-puzzle": CapyPuzzleSolver(),
    "temu-captcha": TemuCaptchaSolver(),
    "lemin-captcha": LeminCaptchaSolver(),
    "binance-captcha": BinanceCaptchaSolver(),
    "tencent-captcha": TencentCaptchaSolver(),
    # PoW / sans-friction
    "altcha": AltchaSolver(),
    "friendly-captcha": FriendlyCaptchaSolver(),
    "captchafox": CaptchaFoxSolver(),
    "mtcaptcha": MTCaptchaSolver(),
    "prosopo-procaptcha": ProsopoSolver(),
    # Bot-protection
    "datadome-captcha": DataDomeSolver(),
    "imperva-captcha": ImpervaSolver(),
}

__all__ = ["BaseSolver", "SolverContext", "SolverResult", "REGISTRY"]
