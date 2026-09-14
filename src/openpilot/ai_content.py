from __future__ import annotations

import json
import os
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


def _provider() -> str:
    return os.getenv("OPENPILOT_AI_PROVIDER", "local").strip().lower()


def _local_model() -> str:
    return os.getenv("OPENPILOT_LOCAL_MODEL", "qwen2.5:3b")


def _ollama_json(prompt: str) -> dict:
    payload = {
        "model": _local_model(), "prompt": prompt, "stream": False, "format": "json",
        "options": {"temperature": 0.1, "num_ctx": 8192},
    }
    req = urllib.request.Request(
        os.getenv("OPENPILOT_OLLAMA_URL", "http://127.0.0.1:11434/api/generate"),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    timeout = max(30, min(600, int(os.getenv("OPENPILOT_AI_TIMEOUT", "180"))))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (socket.timeout, TimeoutError) as exc:
        raise RuntimeError(f"Local AI timed out after {timeout}s using '{_local_model()}'.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Local AI unavailable. Start Ollama and install '{_local_model()}'. Details: {exc.reason}") from exc
    text = str(data.get("response", "")).strip()
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
        f"{base}/{path.lstrip('/')}", data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode())
    except (socket.timeout, TimeoutError) as exc:
        raise RuntimeError(f"OpenAI API timed out while calling {path}.") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()[:600]
        raise RuntimeError(f"OpenAI API {exc.code} ({path}): {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API connection error ({path}): {exc.reason}") from exc


def _chat_json(prompt: str, model: str | None = None) -> dict:
    if _provider() == "local":
        return _ollama_json(prompt)
    model = model or os.getenv("OPENPILOT_MODEL", "gpt-5-mini")
    data = _openai_request("chat/completions", {
        "model": model, "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    })
    return json.loads(data["choices"][0]["message"]["content"])


def _translate_batch(texts: list[str], model: str | None = None) -> list[str]:
    payload = json.dumps(texts, ensure_ascii=False)
    prompt = (
        "You are a professional Vietnamese subtitle translator. Translate each item independently into "
        "natural spoken Vietnamese. Preserve names, numbers, tone and factual meaning. Do not summarize, "
        "merge, invent, or add explanations. If a source item is clearly noise or meaningless ASR, return "
        "an empty string for that item. Return JSON exactly {\"items\":[string,...]} with the same count.\n"
        f"ITEMS={payload}"
    )
    result = _chat_json(prompt, model)
    items = result.get("items")
    if not isinstance(items, list) or len(items) != len(texts):
        raise RuntimeError("AI translation returned an unexpected number of segments.")
    return [" ".join(str(x or "").split()).strip() for x in items]


def translate_segments(texts: list[str], model: str | None = None) -> list[str]:
    if not texts:
        return []
    batch_size = max(2, min(8, int(os.getenv("OPENPILOT_TRANSLATION_BATCH", "6"))))
    output: list[str] = []
    for start in range(0, len(texts), batch_size):
        output.extend(_translate_batch(texts[start:start + batch_size], model))
    return output


def generate_narration(source_text: str, duration_seconds: float, model: str | None = None) -> str:
    """Create a polished Vietnamese voice-over that intentionally covers the full video."""
    source_text = " ".join(source_text.split()).strip()
    duration = max(5.0, float(duration_seconds or 5.0))
    if not source_text:
        raise RuntimeError("Cannot create narration from empty source text.")

    # Vietnamese narration at a calm social-video pace is roughly 2.1-2.4 words/sec.
    target_words = max(18, int(duration * 2.25))
    prompt = (
        "You are a senior Vietnamese short-form video narrator and editor. Rewrite the SOURCE into ONE "
        "continuous, modern, professional Vietnamese voice-over for the ENTIRE video. This is narration, "
        "not a literal translation and not a summary. Preserve every important factual detail present in "
        "the source, but remove ASR noise, repetition and filler. Do not invent names, numbers, places, "
        "events, opinions or facts. Use a natural Vietnamese spoken style: confident, concise, contemporary, "
        "engaging, with smooth transitions and short sentences. No headings, bullets, emojis, hashtags, "
        "stage directions or quotation marks. Start with a strong but factual opening, explain what viewers "
        "are seeing, and finish with a natural closing sentence. The narration must be long enough to cover "
        f"the FULL {duration:.1f}-second video at about 2.25 Vietnamese words/second: target about {target_words} words. "
        "Return JSON exactly {\"narration\":\"...\"}.\nSOURCE:\n" + source_text
    )
    result = _chat_json(prompt, model)
    narration = " ".join(str(result.get("narration") or "").split()).strip()
    if not narration:
        raise RuntimeError("AI narration returned empty text.")
    return narration


def _normalize_hashtags(value: object) -> list[str]:
    raw = value if isinstance(value, list) else str(value or "").replace(",", " ").split()
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        tag = "".join(str(item).strip().split())
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = "#" + tag
        key = tag.casefold()
        if len(tag) > 40 or key in seen:
            continue
        seen.add(key)
        result.append(tag)
        if len(result) >= 8:
            break
    return result


def _clean_title(value: object, fallback: str) -> str:
    title = " ".join(str(value or "").replace("\n", " ").split()).strip(" \"'“”")
    return (title or " ".join(fallback.split()))[:90].rstrip(" .,!?;:")


def generate_package(source_text: str, model: str | None = None) -> dict:
    source_text = " ".join(source_text.split()).strip()
    if not source_text:
        raise RuntimeError("Cannot generate publishing metadata from empty transcript.")
    prompt = (
        "You are a senior Vietnamese short-video editor. Return JSON only with keys translation, title, "
        "description, hashtags. The source may contain imperfect ASR. Never repeat obvious noise or random "
        "words. translation must preserve the source meaning without invention. title must be natural Vietnamese "
        "and 8-70 characters. description must be factual and concise. hashtags must be 5-8 unique Vietnamese "
        "hashtags relevant to the actual source. Do not invent names, locations, events or claims.\nSOURCE:\n" + source_text
    )
    result = _chat_json(prompt, model)
    translation = " ".join(str(result.get("translation") or source_text).split())
    title = _clean_title(result.get("title"), translation[:70])
    description = " ".join(str(result.get("description") or translation).split())[:500]
    hashtags = _normalize_hashtags(result.get("hashtags"))
    for tag in ("#TinTuc", "#VideoNgan", "#VietNam", "#NoiDungHay", "#XuHuong"):
        if len(hashtags) >= 5:
            break
        if tag.casefold() not in {x.casefold() for x in hashtags}:
            hashtags.append(tag)
    return {"translation": translation, "title": title, "description": description, "hashtags": hashtags}


def _piper_speech(text: str, output_file: str | Path) -> Path:
    model = os.getenv("PIPER_MODEL")
    if not model:
        raise RuntimeError("Local TTS needs PIPER_MODEL. Set OPENPILOT_TTS_PROVIDER=pyttsx3 for Windows system speech.")
    piper = os.getenv("PIPER_COMMAND", "piper")
    target = Path(output_file); target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([piper, "--model", model, "--output_file", str(target)], input=text, text=True, check=True, capture_output=True, timeout=300)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Local Piper TTS failed: {exc}") from exc
    return target


def _pyttsx3_speech(text: str, output_file: str | Path) -> Path:
    try:
        import pyttsx3
    except ImportError as exc:
        raise RuntimeError("Install pyttsx3 with: pip install pyttsx3") from exc
    target = Path(output_file); target.parent.mkdir(parents=True, exist_ok=True)
    engine = pyttsx3.init()
    engine.setProperty("rate", int(os.getenv("OPENPILOT_TTS_RATE", "175")))
    engine.save_to_file(text, str(target)); engine.runAndWait()
    if not target.exists() or target.stat().st_size < 1024:
        raise RuntimeError("Windows system TTS did not create a usable audio file.")
    return target


def synthesize_speech(text: str, output_file: str | Path) -> Path:
    text = " ".join(text.split()).strip()
    if not text:
        raise RuntimeError("Cannot synthesize an empty Vietnamese narration.")
    if _provider() == "local":
        if os.getenv("OPENPILOT_TTS_PROVIDER", "piper").lower() == "pyttsx3":
            return _pyttsx3_speech(text, output_file)
        return _piper_speech(text, output_file)
    model = os.getenv("OPENPILOT_TTS_MODEL", "gpt-4o-mini-tts")
    voice = os.getenv("OPENPILOT_TTS_VOICE", "alloy")
    key = os.getenv("OPENPILOT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Missing OPENPILOT_API_KEY or OPENAI_API_KEY for AI voice.")
    base = os.getenv("OPENPILOT_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    req = urllib.request.Request(f"{base}/audio/speech", data=json.dumps({"model": model, "voice": voice, "input": text, "response_format": "mp3"}).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    target = Path(output_file); target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(req, timeout=180) as response, target.open("wb") as stream:
            stream.write(response.read())
    except (socket.timeout, TimeoutError) as exc:
        raise RuntimeError("OpenAI TTS timed out while generating the voice.") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()[:600]
        raise RuntimeError(f"OpenAI API {exc.code} (/audio/speech): {detail or exc.reason}") from exc
    return target
