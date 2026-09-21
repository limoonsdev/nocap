"""NoCap startup banner + log convention.

NOTE: named `log` (not `logging`) on purpose — a `logging.py` inside the
package would shadow the standard library `logging` module whenever this
directory ends up first on `sys.path`, breaking third-party imports.

Convention (stdout, plain ASCII for Windows cp1252 safety):
    [+] positive log
    [-] negative log
    [\\] warning / third-party info / hint
"""
from __future__ import annotations

NOCAP_BANNER = r"""
 _   _      ____
| \ | | ___/ ___|__ _ _ __
|  \| |/ _ \ |   / _` | '_ \
| |\  | (_) | |_| (_| | |_) |
|_| \_|\___/ \___\__,_| .__/
                       |_|
 NoCap - local captcha solver
""".strip("\n")


def banner() -> None:
    """Print the NoCap ASCII banner."""
    print(NOCAP_BANNER, flush=True)


def ok(msg: str) -> None:
    """Positive log."""
    print(f"[+] {msg}", flush=True)


def err(msg: str) -> None:
    """Negative log."""
    print(f"[-] {msg}", flush=True)


def info(msg: str) -> None:
    """Warning / third-party info / hint log."""
    print(r"[\] " + str(msg), flush=True)
