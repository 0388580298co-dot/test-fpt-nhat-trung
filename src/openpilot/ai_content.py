from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path


def _api_request(path: str, payload: dict) -> dict:
    key = os.getenv("OPENPILOT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Missing OPENPILOT_API_KEY or OPENAI_API_KEY.")
    base = os.getenv("OPENPILOT_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    req = urllib.request.Request(
        f"{base}/{path.lstrip('/')}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode())


def generate_package(source_text: str, model: str | None = None) -> dict:
    model = model or os.getenv("OPENPILOT_MODEL", "gpt-5-mini")
    prompt = (
        "Return JSON only with keys translation, title, description, hashtags. "
        "Translate the supplied text naturally into Vietnamese. Create a short, "
        "non-clickbait Vietnamese title, description and 5-10 relevant hashtags. "
        "Do not invent factual claims. Text:\n" + source_text
    )
    data = _api_request("chat/completions", {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    })
    return json.loads(data["choices"][0]["message"]["content"])


def synthesize_speech(text: str, output_file: str | Path) -> Path:
    model = os.getenv("OPENPILOT_TTS_MODEL", "gpt-4o-mini-tts")
    voice = os.getenv("OPENPILOT_TTS_VOICE", "alloy")
    key = os.getenv("OPENPILOT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Missing OPENPILOT_API_KEY or OPENAI_API_KEY for AI voice.")
    base = os.getenv("OPENPILOT_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload = {"model": model, "voice": voice, "input": text, "response_format": "mp3"}
    req = urllib.request.Request(
        f"{base}/audio/speech", data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST"
    )
    target = Path(output_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=180) as response, target.open("wb") as stream:
        stream.write(response.read())
    return target
