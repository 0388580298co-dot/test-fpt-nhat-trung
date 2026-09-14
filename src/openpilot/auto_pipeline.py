from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .ai_content import generate_package, synthesize_speech, translate_segments
from .media import make_vertical, probe
from .official_publishers import publish_tiktok, publish_youtube
from .subtitles import write_srt
from .transcription import TranscriptSegment, transcribe


@dataclass
class AutoResult:
    trend: str
    source_url: str
    input_video: str
    subtitle_file: str
    output_video: str
    status: str
    title: str = ""
    hashtags: str = ""
    message: str = ""
    published: str = ""


def _get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(url, headers=headers or {"User-Agent": "OpenPilot-Studio/0.5"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def discover_trend() -> str:
    key = os.getenv("YOUTUBE_API_KEY")
    query = os.getenv("OPENPILOT_TREND_QUERY", "trending vietnam")
    if not key:
        raise RuntimeError("Missing YOUTUBE_API_KEY. Add an official YouTube Data API key first.")
    params = urllib.parse.urlencode({"part": "snippet", "q": query, "type": "video", "order": "date", "maxResults": "10", "key": key})
    data = _get_json(f"https://www.googleapis.com/youtube/v3/search?{params}")
    items = data.get("items", [])
    if not items:
        raise RuntimeError("Trend Engine found no recent videos for the configured query.")
    return items[0].get("snippet", {}).get("title", query)


def _has_audio(path: Path) -> bool:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def acquire_video(query: str, output_dir: Path) -> tuple[Path, str]:
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("Missing PEXELS_API_KEY. Configure a permitted video source before auto mode.")
    params = urllib.parse.urlencode({"query": query, "per_page": "10", "orientation": "portrait"})
    data = _get_json(f"https://api.pexels.com/videos/search?{params}", headers={"Authorization": key, "User-Agent": "OpenPilot-Studio/0.5"})
    for item in data.get("videos", []):
        for file_info in item.get("video_files", []):
            link = file_info.get("link")
            if not link or file_info.get("width", 0) < 720:
                continue
            output_dir.mkdir(parents=True, exist_ok=True)
            target = output_dir / f"source-{item['id']}.mp4"
            request = urllib.request.Request(link, headers={"User-Agent": "OpenPilot-Studio/0.5"})
            with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as stream:
                stream.write(response.read())
            # Stock footage is allowed to be silent. Keep it and let the AI voice
            # become the narration source instead of forcing Whisper to decode it.
            return target, link
    raise RuntimeError("The permitted video source returned no usable video.")


def _segments_from_script(text: str, duration: float | None) -> list[TranscriptSegment]:
    clean = " ".join(text.split())
    if not clean:
        return []
    total = max(float(duration or 5.0), 5.0)
    sentences = [part.strip() for part in clean.replace("!", ".").replace("?", ".").split(".") if part.strip()]
    if not sentences:
        sentences = [clean]
    step = total / len(sentences)
    return [TranscriptSegment(i * step, min(total, (i + 1) * step), sentence) for i, sentence in enumerate(sentences)]


def _mux_voice(video: Path, voice: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(video), "-i", str(voice), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest", str(output)], check=True, capture_output=True, text=True)
    return output


def run_auto(output_dir: str = "output", whisper_model: str = "small") -> AutoResult:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    trend = discover_trend()
    source, source_url = acquire_video(trend, out / "source")

    if _has_audio(source):
        segments = transcribe(source, whisper_model)
        source_text = " ".join(s.text for s in segments)
        package = generate_package(source_text or trend)
        translated = translate_segments([s.text for s in segments]) if segments else [str(package.get("translation", trend))]
        for seg, vi in zip(segments, translated):
            seg.vietnamese = vi
    else:
        # Pexels stock footage often has no audio. Generate a Vietnamese narration
        # script from the discovered trend instead of treating missing audio as fatal.
        package = generate_package(trend)
        narration = str(package.get("translation") or trend).strip()
        info = probe(source)
        segments = _segments_from_script(narration, info.duration)
        for seg in segments:
            seg.vietnamese = seg.text

    subtitle = write_srt(segments, out / f"{source.stem}.vi.srt")
    vertical = make_vertical(source, out / f"{source.stem}.vertical.mp4")
    title = str(package.get("title", trend)).strip()
    hashtags = package.get("hashtags", [])
    hashtag_text = " ".join(hashtags) if isinstance(hashtags, list) else str(hashtags)
    narration_text = " ".join(getattr(s, "vietnamese", s.text) for s in segments).strip()
    if not narration_text:
        narration_text = str(package.get("translation") or trend).strip()
    voice = synthesize_speech(narration_text, out / f"{source.stem}.vi.mp3")
    voiced = _mux_voice(Path(vertical), voice, out / f"{source.stem}.final.mp4")

    publish_mode = os.getenv("OPENPILOT_PUBLISH", "none").lower()
    published = "not_requested"
    status = "ready_for_publish"
    if publish_mode == "tiktok":
        published = publish_tiktok(str(voiced), f"{title} {hashtag_text}".strip())
        status = "published"
    elif publish_mode == "youtube":
        published = publish_youtube(str(voiced), title, f"{package.get('description', '')}\n\n{hashtag_text}")
        status = "published"
    elif publish_mode not in {"none", "tiktok", "youtube"}:
        raise RuntimeError("OPENPILOT_PUBLISH must be none, tiktok, or youtube.")

    (out / "auto-result.json").write_text(json.dumps({"trend": trend, "source_url": source_url, "input_video": str(source), "subtitle_file": str(subtitle), "output_video": str(voiced), "title": title, "hashtags": hashtag_text, "published": published, "status": status}, ensure_ascii=False, indent=2), encoding="utf-8")
    return AutoResult(trend, source_url, str(source), str(subtitle), str(voiced), status, title, hashtag_text, "Automatic AI translation, voice, packaging and render completed.", published)
