"""Optional LLM provider adapters for OpenPilot."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    pass


class LLMProvider:
    name = "base"

    def generate(self, prompt: str, *, system: str = "") -> str:
        raise NotImplementedError


@dataclass
class OpenAICompatibleProvider(LLMProvider):
    """Adapter for OpenAI-compatible chat completion APIs."""
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    name: str = "openai-compatible"

    def generate(self, prompt: str, *, system: str = "") -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system or "You are OpenPilot, a safe coding agent."},
                {"role": "user", "content": prompt},
            ],
        }
        request = Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ProviderError(f"Provider request failed: {exc}") from exc
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Provider returned an unexpected response") from exc


def provider_from_env() -> LLMProvider | None:
    key = os.getenv("OPENPILOT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    return OpenAICompatibleProvider(
        api_key=key,
        model=os.getenv("OPENPILOT_MODEL", "gpt-5-mini"),
        base_url=os.getenv("OPENPILOT_BASE_URL", "https://api.openai.com/v1"),
    )
