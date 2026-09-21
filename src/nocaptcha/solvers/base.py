"""Contrat commun des solvers."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class SolverContext:
    sitekey: Optional[str] = None
    url: Optional[str] = None
    proxy: Optional[str] = None
    timeout: int = 90
    enterprise: bool = False
    action: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class SolverResult:
    ok: bool
    token: Optional[str] = None
    selected_ids: Optional[list[Any]] = None
    text: Optional[str] = None
    coords: Optional[list[int]] = None
    confidence: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)
    ms: int = 0

class BaseSolver:
    name: str = "base"
    method: str = "local-ai"
    notes: str = ""

    def capabilities(self) -> dict:
        return {"type": self.name, "supported": True, "method": self.method, "local": True, "notes": self.notes}

    async def solve(self, ctx: SolverContext) -> SolverResult:
        raise NotImplementedError
