"""NoCaptcha Python client — zero dependencies (stdlib only).

Works with any Python 3.8+ without installing anything:

    from nocaptcha_client import NoCaptchaClient

    api = NoCaptchaClient()  # http://127.0.0.1:7888
    res = api.ocr("captcha.png", kind="amazon")
    print(res["text"])

    # hCaptcha token flow (see examples/hcaptcha-token-flow.py)
    res = api.token("hcaptcha", sitekey="xxx", url="https://example.com")
    print(res["token"])
"""
from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
import urllib.error
import urllib.request
import uuid

__version__ = "0.1.0"


class NoCaptchaError(Exception):
    """Raised on transport errors (connection refused, HTTP 4xx/5xx)."""


def image_to_b64(image) -> str:
    """Accept a file path, an http(s) URL (returned as-is marker), raw bytes,
    or an already-base64 string, and return a base64 string.

    Returns (b64, is_url). URLs are NOT downloaded: use image_url instead.
    """
    if isinstance(image, (bytes, bytearray)):
        return base64.b64encode(bytes(image)).decode()
    if isinstance(image, str) and image.startswith(("http://", "https://")):
        raise ValueError("pass URLs via the image_url parameter, not image")
    if isinstance(image, str) and os.path.exists(image):
        with open(image, "rb") as f:
            return base64.b64encode(f.read()).decode()
    if isinstance(image, str):
        # assume already base64 (validates)
        try:
            base64.b64decode(image.split(";base64,", 1)[-1] if ";base64," in image else image)
            return image
        except Exception:  # noqa: BLE001 - any decode failure means "not base64"
            raise ValueError(f"not a file path, URL or base64: {image[:60]}")
    raise TypeError(f"unsupported image input: {type(image)}")


class NoCaptchaClient:
    """Thin wrapper over the NoCaptcha universal API."""

    def __init__(self, base_url: str = "http://127.0.0.1:7888", timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ---------- transport ----------
    def _post_json(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(self.base_url + path, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode()
            except Exception:  # noqa: BLE001 - best-effort error body
                body = ""
            raise NoCaptchaError(f"HTTP {e.code}: {body[:300]}")
        except urllib.error.URLError as e:
            raise NoCaptchaError(f"connection failed ({self.base_url}): {e.reason}")

    def _post_file(self, path: str, fields: dict, files: dict) -> dict:
        """Multipart upload. files: {name: (filename, bytes, content_type)}."""
        boundary = uuid.uuid4().hex
        buf = io.BytesIO()
        for k, v in fields.items():
            if v is None:
                continue
            buf.write(f"--{boundary}\r\n".encode())
            buf.write(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
            buf.write(f"{v}\r\n".encode())
        for k, (fname, content, ctype) in files.items():
            buf.write(f"--{boundary}\r\n".encode())
            buf.write(f'Content-Disposition: form-data; name="{k}"; filename="{fname}"\r\n'.encode())
            buf.write(f"Content-Type: {ctype}\r\n\r\n".encode())
            buf.write(content + b"\r\n")
        buf.write(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            self.base_url + path, data=buf.getvalue(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode()
            except Exception:  # noqa: BLE001 - best-effort error body
                body = ""
            raise NoCaptchaError(f"HTTP {e.code}: {body[:300]}")
        except urllib.error.URLError as e:
            raise NoCaptchaError(f"connection failed ({self.base_url}): {e.reason}")

    def _get(self, path: str) -> dict:
        try:
            with urllib.request.urlopen(self.base_url + path, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.URLError as e:
            raise NoCaptchaError(f"connection failed ({self.base_url}): {e.reason}")

    @staticmethod
    def _read_file(path: str) -> tuple[str, bytes, str]:
        with open(path, "rb") as f:
            content = f.read()
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return os.path.basename(path), content, ctype

    # ---------- universal ----------
    def solve(self, type: str, image=None, image_url: str | None = None,
              image2=None, instruction: str | None = None, sitekey: str | None = None,
              url: str | None = None, langs: str = "en", timeout: int = 90,
              **data) -> dict:
        """Universal solver. `type` is required (see capabilities()).
        Image via file path / bytes / base64 (`image`), URL (`image_url`),
        or browser flow (`sitekey` + `url`)."""
        payload: dict = {"type": type, "langs": langs, "timeout": timeout, "data": data or {}}
        if image is not None:
            payload["image_b64"] = image_to_b64(image)
        if image_url:
            payload["image_url"] = image_url
        if image2 is not None:
            payload["image_b64_2"] = image_to_b64(image2)
        if instruction:
            payload["instruction"] = instruction
        if sitekey:
            payload["sitekey"] = sitekey
        if url:
            payload["url"] = url
        return self._post_json("/v1/solve", payload)

    def solve_file(self, type: str, path: str, piece_path: str | None = None,
                   instruction: str | None = None, timeout: int = 90) -> dict:
        """Universal solver via raw file upload (no base64 needed)."""
        files = {"file": self._read_file(path)}
        if piece_path:
            files["file2"] = self._read_file(piece_path)
        fields = {"type": type, "timeout": str(timeout)}
        if instruction:
            fields["instruction"] = instruction
        return self._post_file("/v1/solve/file", fields, files)

    # ---------- shortcuts ----------
    def ocr(self, image=None, image_url: str | None = None,
            kind: str = "auto", langs: str = "en") -> dict:
        payload: dict = {"kind": kind, "langs": langs}
        if image is not None:
            payload["image_b64"] = image_to_b64(image)
        if image_url:
            payload["image_url"] = image_url
        return self._post_json("/v1/solve/ocr", payload)

    def slider(self, bg, piece=None) -> dict:
        payload = {"bg_b64": image_to_b64(bg)}
        if piece is not None:
            payload["piece_b64"] = image_to_b64(piece)
        return self._post_json("/v1/solve/slider", payload)

    def click(self, image=None, image_url: str | None = None, instruction: str = "") -> dict:
        payload = {"instruction": instruction}
        if image is not None:
            payload["image_b64"] = image_to_b64(image)
        if image_url:
            payload["image_url"] = image_url
        return self._post_json("/v1/solve/click", payload)

    def token(self, type: str, sitekey: str, url: str, timeout: int = 120) -> dict:
        """Browser token flow: returns {"token": ...} to inject into the page."""
        return self._post_json("/v1/solve", {"type": type, "sitekey": sitekey,
                                             "url": url, "timeout": timeout, "data": {}})

    def math(self, text: str | None = None, image=None) -> dict:
        payload: dict = {}
        if text:
            payload["text"] = text
        if image is not None:
            payload["image_b64"] = image_to_b64(image)
        return self._post_json("/v1/solve/math", payload)

    # ---------- system ----------
    def health(self) -> dict:
        return self._get("/v1/health")

    def capabilities(self) -> list:
        return self._get("/v1/capabilities")

    def stats(self) -> dict:
        return self._get("/v1/stats")
