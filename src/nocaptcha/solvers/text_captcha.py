"""OCR/text family: Normal, Text, Number, Russian, Chinese, Amazon, VK, ATB, Math.

All 100% local: CLAHE preprocessing + cascade engine (RapidOCR/EasyOCR/Tesseract).
Differences: languages, whitelist, post-processing (digits, math eval, amazon 6-char).
"""
from __future__ import annotations
import re
import time
from PIL import Image
from .base import BaseSolver, SolverContext, SolverResult
from ..ai.ocr import LocalOcr
from ..ai.math_solver import solve_math_text

class _OcrFamily(BaseSolver):
    langs: str = "en"
    whitelist: str | None = None
    kind: str = "auto"
    length: int | None = None

    async def solve_pil(self, img: Image.Image, langs: str | None = None) -> SolverResult:
        t0 = time.time()
        ocr = LocalOcr("auto", langs or self.langs, kind=self.kind)
        text, conf = ocr.read(img, preprocess=True)
        text = self._post(text)
        ms = int((time.time() - t0) * 1000)
        return SolverResult(ok=bool(text), text=text, confidence=conf,
                            detail={"backend": ocr.active, "kind": self.kind}, ms=ms)

    def _post(self, t: str) -> str:
        t = t.strip().replace(" ", "")
        if self.whitelist:
            t = "".join(c for c in t if c in self.whitelist)
        if self.length:
            t = t[:self.length]
        return t

    async def solve(self, ctx: SolverContext) -> SolverResult:
        # browser fallback: extract the image via JS when a url is provided
        if ctx.url:
            try:
                from ..browser import get_driver
                async with get_driver(headless=None) as page:
                    await page.goto(ctx.url)
                    return SolverResult(ok=False, detail={"hint": f"pass the image as base64 to POST /v1/solve/ocr (kind={self.kind})"}, ms=0)
            except Exception as e:
                return SolverResult(ok=False, detail={"error": str(e)}, ms=0)
        return SolverResult(ok=False, detail={"hint": f"POST /v1/solve/ocr kind={self.kind}"}, ms=0)

class NormalCaptchaSolver(_OcrFamily):
    name = "normal-captcha"; kind = "normal"; langs = "en"
    method = "Generic local OCR + denoise"; notes = "Standard 4-6 char text captcha."

class TextCaptchaSolver(_OcrFamily):
    name = "text-captcha"; kind = "text"; langs = "fr,en"
    method = "Local FR/EN OCR"; notes = "Generic distorted text."

class NumberCaptchaSolver(_OcrFamily):
    name = "number-captcha"; kind = "number"; langs = "en"; whitelist = "0123456789"
    method = "MNIST ONNX (26 Ko) + OCR digits whitelist"; notes = "Chiffres : segmentation + MNIST, fallback OCR."

    async def solve_pil(self, img: Image.Image, langs: str | None = None) -> SolverResult:
        t0 = time.time()
        try:
            from ..ai.onnx_zoo import mnist_read
            txt, conf = mnist_read(img)
            if txt and conf >= 0.5:
                ms = int((time.time() - t0) * 1000)
                return SolverResult(ok=True, text=txt, confidence=conf,
                                    detail={"backend": "mnist-12.onnx", "kind": self.kind}, ms=ms)
        except Exception:
            pass
        base = await super().solve_pil(img, langs)
        if base.detail.get("backend") != "mnist-12.onnx":
            base.detail["mnist_tried"] = True
        return base

class RussianCaptchaSolver(_OcrFamily):
    name = "russian-captcha"; kind = "russian"; langs = "ru,en"
    method = "Cyrillic OCR (RapidOCR/EasyOCR ru + Tesseract rus)"; notes = "Handles А-Я + digits."
    def _post(self, t: str) -> str:
        return t.strip().replace(" ", "")

class ChineseCaptchaSolver(_OcrFamily):
    name = "chinese-captcha"; kind = "chinese"; langs = "zh,en"
    method = "Chinese OCR (chi_sim) + digits/latin"; notes = "Characters + digits."
    def _post(self, t: str) -> str:
        return t.strip().replace(" ", "")

class AmazonCaptchaSolver(_OcrFamily):
    name = "amazon-captcha"; kind = "amazon"; langs = "en"
    whitelist = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"; length = 6
    method = "OCR + Amazon whitelist (no I,O,0,1) + x2 upscale"; notes = "6 noisy Amazon characters."
    def _post(self, t: str) -> str:
        t = super()._post(t)
        return re.sub(r"[^A-Za-z2-9]", "", t)[:6]

class VkCaptchaSolver(_OcrFamily):
    name = "vk-captcha"; kind = "vk"; langs = "ru,en"; whitelist = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZабвгдежзийклмнопрстуфхцчшщэюя"
    method = "VK OCR (latin + cyrillic)"; notes = "VK.com 4-5 characters."

class AtbCaptchaSolver(_OcrFamily):
    name = "atb-captcha"; kind = "atb"; langs = "en"
    method = "ATB OCR + normalization"; notes = "Standard ATB Captcha."

class MathCaptchaSolver(_OcrFamily):
    name = "math-captcha"; kind = "math"; langs = "fr,en"
    method = "OCR + FR/EN arithmetic eval (2+3, five x 4)"; notes = "Answers the result, not the expression."
    async def solve_pil(self, img: Image.Image, langs: str | None = None) -> SolverResult:
        base = await super().solve_pil(img, langs)
        if not base.ok:
            return base
        ans, conf = solve_math_text(base.text or "")
        if ans is None:
            return SolverResult(ok=False, text=base.text, confidence=0.2, detail={"raw": base.text, "error": "unreadable expression"}, ms=base.ms)
        return SolverResult(ok=True, text=ans, confidence=max(conf, base.confidence * 0.9),
                            detail={"raw": base.text, "backend": base.detail.get("backend")}, ms=base.ms)
