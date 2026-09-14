from __future__ import annotations

import json
import os
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


def _provider() -> str:
    # Local AI is the reliable default for the fully local pipeline.
    return os.getenv("OPENPILOT_AI_PROVIDER", "local").strip().lower()


def _local_model() -> str:
    return os.getenv("OPENPILOT_LOCAL_MODEL", "qwen2.5:3b")


def _ollama_json(prompt: str) -> dict:
    """Run a JSON-producing prompt against a local Ollama server."""
    payload = {
        "model": _local_model(),
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }
    req = urllib.request.Request(
        os.getenv("OPENPILOT_OLLAMA_URL", "http://127.0.0.1:11434/api/generate"),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
    except socket.timeout as exc:
        raise RuntimeError(
            f"Local AI timed out after 180 seconds while using '{_local_model()}'. "
            "Make sure Ollama is running and the model is available; a smaller model such as qwen2.5:3b is recommended."
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(
            f"Local AI timed out after 180 seconds while using '{_local_model()}'. "
            "Make sure Ollama is running and the model is available."
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            "Local AI is unavailable. Start Ollama and install the model "
            f"'{_local_model()}', then run openpilot auto again. Details: {exc.reason}"
        ) from exc
    text = data.get("response", "").strip()
    if not text:
        raise RuntimeError("Local AI returned an empty response.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Local AI returned invalid JSON. Try a stronger local model.") from exc


def _openai_request(path: str, payload: dict) -> dict:
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
    except socket.timeout as exc:
        raise RuntimeError(f"OpenAI API timed out while calling {path}.") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"OpenAI API timed out while calling {path}.") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if len(detail) > 600:
            detail = detail[:600]
        raise RuntimeError(f"OpenAI API {exc.code} ({path}): {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API connection error ({path}): {exc.reason}") from exc


def _chat_json(prompt: str, model: str | None = None) -> dict:
    if _provider() == "local":
        return _ollama_json(prompt)
    model = model or os.getenv("OPENPILOT_MODEL", "gpt-5-mini")
    data = _openai_request(
        "chat/completions",
        {"model": model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}},
    )
    return json.loads(data["choices"][0]["message"]["content"])


def translate_segments(texts: list[str], model: str | None = None) -> list[str]:
    if not texts:
        return []
    result = _chat_json(
        "Translate every item into natural Vietnamese. Preserve meaning and return JSON as "
        "{\"items\":[strings]}. Items:\n" + json.dumps(texts, ensure_ascii=False), model
    )
    items = result.get("items", [])
    if len(items) != len(texts):
        raise RuntimeError("AI translation returned an unexpected number of segments.")
    return [str(x).strip() for x in items]


def generate_package(source_text: str, model: str | None = None) -> dict:
    return _chat_json(
        "Return JSON only with keys translation, title, description, hashtags. "
        "Translate the supplied text naturally into Vietnamese. Create a short, "
        "non-clickbait Vietnamese title, description and 5-10 relevant hashtags. "
        "Do not invent factual claims. Text:\n" + source_text,
        model,
    )


def _piper_speech(text: str, output_file: str | Path) -> Path:
    model = os.getenv("PIPER_MODEL")
    if not model:
        raise RuntimeError(
            "Local TTS needs PIPER_MODEL pointing to a Vietnamese Piper .onnx model. "
            "Set OPENPILOT_TTS_PROVIDER=pyttsx3 for Windows system speech instead."
        )
    piper = os.getenv("PIPER_COMMAND", "piper")
    target = Path(output_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [piper, "--model", model, "--output_file", str(target)],
            input=text,
            text=True,
            check=True,
            capture_output=True,
            timeout=300,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Local Piper TTS failed: {exc}") from exc
    return target


def _pyttsx3_speech(text: str, output_file: str | Path) -> Path:
    try:
        import pyttsx3
    except ImportError as exc:
        raise RuntimeError("Install pyttsx3 with: pip install pyttsx3") from exc
    target = Path(output_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    engine = pyttsx3.init()
    engine.save_to_file(text, str(target))
    engine.runAndWait()
    if not target.exists() or target.stat().st_size == 0:
        raise RuntimeError("Windows system TTS did not create an audio file.")
    return target


def synthesize_speech(text: str, output_file: str | Path) -> Path:
    if _provider() == "local":
        tts_provider = os.getenv("OPENPILOT_TTS_PROVIDER", "piper").lower()
        if tts_provider == "pyttsx3":
            return _pyttsx3_speech(text, output_file)
        return _piper_speech(text, output_file)

    model = os.getenv("OPENPILOT_TTS_MODEL", "gpt-4o-mini-tts")
    voice = os.getenv("OPENPILOT_TTS_VOICE", "alloy")
    key = os.getenv("OPENPILOT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Missing OPENPILOT_API_KEY or OPENAI_API_KEY for AI voice.")
    base = os.getenv("OPENPILOT_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    req = urllib.request.Request(
        f"{base}/audio/speech",
        data=json.dumps({"model": model, "voice": voice, "input": text, "response_format": "mp3"}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    target = Path(output_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(req, timeout=180) as response, target.open("wb") as stream:
            stream.write(response.read())
    except socket.timeout as exc:
        raise RuntimeError("OpenAI TTS timed out while generating the voice.") from exc
    except TimeoutError as exc:
        raise RuntimeError("OpenAI TTS timed out while generating the voice.") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if len(detail) > 600:
            detail = detail[:600]
        raise RuntimeError(f"OpenAI API {exc.code} (/audio/speech): {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API connection error (/audio/speech): {exc.reason}") from exc
    return target
