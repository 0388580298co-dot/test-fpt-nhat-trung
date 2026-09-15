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
        "Bạn là biên tập viên phụ đề tiếng Việt chuyên nghiệp cho video ngắn. "
        "Dịch từng mục sang tiếng Việt TỰ NHIÊN, dễ nghe khi đọc thành tiếng, giống cách người Việt nói hằng ngày. "
        "Không dịch từng từ theo kiểu máy móc. Giữ đúng chủ thể, tên riêng, số liệu, địa danh, thời gian và ý chính. "
        "Có thể đổi trật tự từ để câu tiếng Việt tự nhiên hơn nhưng tuyệt đối không được tự thêm thông tin. "
        "Loại bỏ tiếng đệm, lặp từ, lỗi nhận dạng giọng nói và câu vô nghĩa. Không tóm tắt. Không ghép các mục với nhau. "
        "Mỗi mục chỉ trả về một câu hoặc cụm câu ngắn, có dấu câu tiếng Việt chuẩn. Nếu mục là tiếng ồn hoặc ASR không thể hiểu, trả về chuỗi rỗng. "
        "Trả JSON CHÍNH XÁC dạng {\"items\":[string,...]} và phải có đúng số lượng mục đầu vào.\n"
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


def _polish_narration_batch(source: str, model: str | None = None) -> str:
    """Light editorial pass: improve spoken Vietnamese without inventing or summarising."""
    prompt = (
        "Bạn là biên tập viên lời dẫn video Việt Nam. Hãy BIÊN TẬP đoạn SOURCE dưới đây thành lời thuyết minh "
        "tự nhiên để đọc bằng giọng AI. Đây là biên tập, KHÔNG phải sáng tác.\n"
        "QUY TẮC BẮT BUỘC:\n"
        "1. Giữ nguyên thứ tự thông tin và toàn bộ ý quan trọng của SOURCE.\n"
        "2. Không bịa thêm bất kỳ tên, số liệu, địa điểm, nguyên nhân, nhận xét hoặc kết luận nào.\n"
        "3. Không tóm tắt và không kéo dài câu chỉ để đủ thời lượng.\n"
        "4. Xóa từ lặp, lỗi Whisper, tiếng đệm và câu vô nghĩa.\n"
        "5. Viết như một biên tập viên Việt Nam đang đọc bản tin/phóng sự ngắn: rõ ràng, hiện đại, chắc câu, không văn vẻ.\n"
        "6. Câu chủ động, ngắn vừa phải; ưu tiên 8-20 từ mỗi câu.\n"
        "7. Không dùng các câu sáo rỗng như 'hãy cùng khám phá', 'điều đáng chú ý là', 'không thể bỏ qua' nếu SOURCE không có nội dung tương ứng.\n"
        "8. Không dùng tiêu đề, bullet, emoji, hashtag, lời kêu gọi tương tác.\n"
        "9. Nếu một câu trong SOURCE không chắc nghĩa, giữ cách diễn đạt trung tính thay vì đoán.\n"
        "Trả JSON CHÍNH XÁC: {\"narration\":\"...\"}.\n"
        "SOURCE:\n" + source
    )
    result = _chat_json(prompt, model)
    return " ".join(str(result.get("narration") or "").split()).strip()


def _quality_check_narration(text: str) -> str:
    clean = " ".join(text.split()).strip()
    if not clean:
        raise RuntimeError("AI narration returned empty text.")
    words = clean.split()
    if len(words) < 8:
        raise RuntimeError("AI narration is too short to be a useful full-video voice-over.")
    # Reject obvious model artifacts before they reach TTS.
    bad_markers = ("[narration]", "[voiceover]", "json:", "here is", "đây là bản thuyết minh:")
    lowered = clean.casefold()
    if any(marker in lowered for marker in bad_markers):
        raise RuntimeError("AI narration contains a formatting artifact.")
    # Remove accidental repeated adjacent sentences/phrases.
    sentences = [x.strip() for x in __import__("re").split(r"(?<=[.!?…])\s+", clean) if x.strip()]
    deduped: list[str] = []
    for sentence in sentences:
        if not deduped or sentence.casefold() != deduped[-1].casefold():
            deduped.append(sentence)
    return " ".join(deduped)


def generate_narration(source_text: str, duration_seconds: float, model: str | None = None) -> str:
    """Create a factual, spoken Vietnamese narration without forcing the model to invent filler."""
    source_text = " ".join(source_text.split()).strip()
    duration = max(5.0, float(duration_seconds or 5.0))
    if not source_text:
        raise RuntimeError("Cannot create narration from empty source text.")

    # Long one-shot prompts were producing awkward prose on small local models.
    # Work in small editorial blocks, then join them in source order.
    sentences = [x.strip() for x in __import__("re").split(r"(?<=[.!?…])\s+", source_text) if x.strip()]
    if not sentences:
        sentences = [source_text]
    blocks: list[str] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentences:
        count = len(sentence.split())
        if current and current_words + count > 90:
            blocks.append(" ".join(current)); current = []; current_words = 0
        current.append(sentence); current_words += count
    if current:
        blocks.append(" ".join(current))

    polished: list[str] = []
    for block in blocks:
        edited = _polish_narration_batch(block, model)
        if edited:
            polished.append(edited)
    narration = _quality_check_narration(" ".join(polished))

    # If the model is asked for an enormous expansion, the result becomes padded and unnatural.
    # Keep a soft duration sanity check rather than forcing an exact word count.
    max_words = max(20, int(duration * 2.8))
    if len(narration.split()) > max_words:
        trim = _polish_narration_batch(narration, model)
        if trim and len(trim.split()) <= max_words:
            narration = trim
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
    engine.setProperty("rate", int(os.getenv("OPENPILOT_TTS_RATE", "165")))
    engine.setProperty("volume", float(os.getenv("OPENPILOT_TTS_VOLUME", "1.0")))
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
