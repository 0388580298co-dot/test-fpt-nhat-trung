from __future__ import annotations

import json
import os
import urllib.error
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
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if len(detail) > 600:
            detail = detail[:600]
        raise RuntimeError(f"OpenAI API {exc.code} ({path}): {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API connection error ({path}): {exc.reason}") from exc


def _chat_json(prompt: str, model: str | None = None) -> dict:
    model = model or os.getenv("OPENPILOT_MODEL", "gpt-5-mini")
    data = _api_request("chat/completions", {"model": model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}})
    return json.loads(data["choices"][0]["message"]["content"])


def translate_segments(texts: list[str], model: str | None = None) -> list[str]:
    if not texts:
        return []
    result = _chat_json("Translate every item into natural Vietnamese. Preserve meaning and return JSON as {\"items\":[strings]}. Items:\n" + json.dumps(texts, ensure_ascii=False), model)
    items = result.get("items", [])
    if len(items) != len(texts):
        raise RuntimeError("AI translation returned an unexpected number of segments.")
    return [str(x).strip() for x in items]


def generate_package(source_text: str, model: str | None = None) -> dict:
    return _chat_json("Return JSON only with keys translation, title, description, hashtags. Translate the supplied text naturally into Vietnamese. Create a short, non-clickbait Vietnamese title, description and 5-10 relevant hashtags. Do not invent factual claims. Text:\n" + source_text, model)


def synthesize_speech(text: str, output_file: str | Path) -> Path:
    model = os.getenv("OPENPILOT_TTS_MODEL", "gpt-4o-mini-tts")
    voice = os.getenv("OPENPILOT_TTS_VOICE", "alloy")
    key = os.getenv("OPENPILOT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Missing OPENPILOT_API_KEY or OPENAI_API_KEY for AI voice.")
    base = os.getenv("OPENPILOT_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    req = urllib.request.Request(f"{base}/audio/speech", data=json.dumps({"model": model, "voice": voice, "input": text, "response_format": "mp3"}).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    target = Path(output_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(req, timeout=180) as response, target.open("wb") as stream:
            stream.write(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if len(detail) > 600:
            detail = detail[:600]
        raise RuntimeError(f"OpenAI API {exc.code} (/audio/speech): {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API connection error (/audio/speech): {exc.reason}") from exc
    return target
