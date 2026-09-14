from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class TranslationResult:
    source: str
    vietnamese: str


class Translator(Protocol):
    def translate(self, text: str) -> str: ...


class SimpleTranslator:
    """Safe offline starter translator. Replace with an LLM adapter for production."""

    def translate(self, text: str) -> str:
        # Deliberately avoids pretending to be a full machine translator.
        return text


def translate_segments(segments, translator: Translator) -> list[TranslationResult]:
    return [TranslationResult(s.text, translator.translate(s.text)) for s in segments]
