from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class TrendCandidate:
    title: str
    url: str
    platform: str
    score: float
    rights_required: bool = True


class TrendSource(Protocol):
    def trending(self, limit: int = 20) -> list[TrendCandidate]: ...


class ManualTrendSource:
    """Human-approved source adapter; avoids scraping or bypassing platform controls."""

    def __init__(self, candidates: list[TrendCandidate] | None = None):
        self.candidates = candidates or []

    def trending(self, limit: int = 20) -> list[TrendCandidate]:
        return sorted(self.candidates, key=lambda x: x.score, reverse=True)[:limit]
