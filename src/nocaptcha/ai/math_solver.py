"""Math captcha: '2+3=?', 'five x 4', '12 - 7' -> answer. 100% local, no LLM."""
from __future__ import annotations
import re
import unicodedata

FR_NUM = {"zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
          "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12,
          "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20, "trente": 30,
          "quarante": 40, "cinquante": 50}
EN_NUM = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}

def _norm(s: str) -> str:
    s = s.lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = s.replace("x", "*").replace("×", "*").replace("÷", "/").replace(":", "/").replace("=", " ")
    s = s.replace("plus", "+").replace("minus", "-").replace("moins", "-").replace("fois", "*")
    return s

def solve_math_text(text: str) -> tuple[str | None, float]:
    """Return (answer_str, confidence) or (None, 0.0). Safe eval: only + - * / and numbers."""
    n = _norm(text)
    # mots -> chiffres
    for w, v in {**FR_NUM, **EN_NUM}.items():
        n = re.sub(rf"\b{w}\b", str(v), n)
    m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*([+\-*/])\s*(-?\d+(?:[.,]\d+)?)", n)
    if not m:
        # plain number to copy back?
        m2 = re.search(r"-?\d+", n)
        if m2 and len(n.strip()) < 12:
            return m2.group(0), 0.6
        return None, 0.0
    try:
        a = float(m.group(1).replace(",", "."))
        op = m.group(2)
        b = float(m.group(3).replace(",", "."))
        if op == "+": r = a + b
        elif op == "-": r = a - b
        elif op == "*": r = a * b
        elif op == "/":
            if b == 0: return None, 0.0
            r = a / b
        else: return None, 0.0
        out = str(int(r)) if float(r).is_integer() else f"{r:.2f}".rstrip("0").rstrip(".")
        return out, 0.95
    except Exception:
        return None, 0.0
