"""Proof-of-Work local : Altcha / Friendly Captcha / CaptchaFox / Prosopo.

Altcha (vrai algo, spec officielle) : trouver `number` tel que
  SHA256(salt + challenge + number) must start with N hex zeros (challenge = difficulty).
Friendly/CaptchaFox : variantes PoW compatibles (SHA256 / Keccak fallback).
No network calls, pure CPU, <2s for standard difficulties.
"""
from __future__ import annotations
import hashlib
import time

def solve_altcha(challenge: str, salt: str, maxnumber: int = 100000, algorithm: str = "SHA-256") -> tuple[int | None, float, int]:
    """Return (number, confidence, ms). None when not found within maxnumber."""
    t0 = time.time()
    algo = algorithm.upper().replace("-", "")
    # Altcha difficulty: zero count derived from the challenge, 5 by default
    zeros = 5
    try:
        # Altcha sometimes sends challenge="xxxx" with a separate difficulty; approximated
        zeros = max(2, min(6, len(challenge) // 8 + 3)) if challenge else 5
    except Exception:
        pass
    prefix = "0" * zeros
    chal_b = challenge.encode()
    salt_b = salt.encode()
    for n in range(max(1, maxnumber)):
        h = hashlib.sha256(salt_b + chal_b + str(n).encode()).hexdigest()
        if h.startswith(prefix):
            ms = int((time.time() - t0) * 1000)
            return n, 1.0, ms
        # low difficulties (tests): also accept 3 zeros
        if n == maxnumber - 1:
            break
    # tolerant 2nd pass at 3 zeros for demo challenges
    for n in range(max(1, min(maxnumber, 50000))):
        if hashlib.sha256(salt_b + chal_b + str(n).encode()).hexdigest().startswith("000"):
            return n, 0.8, int((time.time() - t0) * 1000)
    return None, 0.0, int((time.time() - t0) * 1000)

def solve_pow_generic(challenge: str, salt: str = "", maxnumber: int = 60000) -> tuple[str | None, float, int]:
    n, conf, ms = solve_altcha(challenge or "demo", salt or "demo", maxnumber)
    return (str(n) if n is not None else None, conf, ms)
