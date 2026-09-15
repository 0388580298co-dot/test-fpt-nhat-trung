from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .ai_content import generate_narration, generate_package, synthesize_speech, translate_segments
from .douyin_acquisition import acquire_douyin_batch
from .media import validate_video, render_final
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
    results: list[dict] = field(default_factory=list)


class AutoUI:
    def __init__(self, total: int):
        self.total = total
        self.started = time.perf_counter()

    @staticmethod
    def line(char: str = "=", width: int = 78) -> None:
        print(char * width, flush=True)

    def header(self) -> None:
        self.line()
        print("  OPENPILOT STUDIO  |  AI CONTENT FACTORY", flush=True)
        print("  DOUYIN -> WHISPER -> VIETNAMESE -> NARRATION -> TTS -> 9:16 -> PUBLISH", flush=True)
        self.line()
        print(f"  Batch        : {self.total:02d} videos", flush=True)
        print("  Source       : Douyin only | duration >10s", flush=True)
        print(f"  AI           : {os.getenv('OPENPILOT_AI_PROVIDER', 'local')}", flush=True)
        print(f"  Local model  : {os.getenv('OPENPILOT_LOCAL_MODEL', 'qwen2.5:3b')}", flush=True)
        print(f"  TTS          : {os.getenv('OPENPILOT_TTS_PROVIDER', 'piper')}", flush=True)
        print(f"  Publishing   : {os.getenv('OPENPILOT_PUBLISH', 'none')}", flush=True)
        self.line("-")

    def phase(self, number: int, title: str, detail: str = "") -> None:
        print(f"\n  [{number}/8] {title}", flush=True)
        if detail:
            print(f"        {detail}", flush=True)

    def item(self, icon: str, message: str) -> None:
        print(f"        {icon:<5} {message}", flush=True)

    def video_header(self, index: int, name: str) -> None:
        print(f"\n  +---------------- VIDEO {index:02d}/{self.total:02d} ----------------+", flush=True)
        print(f"  | {name[:58]}", flush=True)
        print("  +--------------------------------------------------+", flush=True)

    def video_stage(self, stage: int, name: str, started: float) -> None:
        print(f"        [{stage}/5] {name:<36} {time.perf_counter() - started:6.1f}s", flush=True)

    def finish(self, success: int, failed: int) -> None:
        self.line("-")
        print("  RUN SUMMARY", flush=True)
        print(f"  Completed    : {success:02d}/{self.total:02d}", flush=True)
        print(f"  Failed       : {failed:02d}/{self.total:02d}", flush=True)
        print(f"  Elapsed      : {time.perf_counter() - self.started:.1f}s", flush=True)
        print("  Manifest     : output\\auto-manifest.json", flush=True)
        self.line()


def _http_detail(exc: urllib.error.HTTPError) -> str:
    detail = exc.read().decode("utf-8", errors="replace").strip()
    return detail[:600] if detail else str(exc.reason)


def _get_json(url: str, api_name: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "OpenPilot-Studio/0.7"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{api_name} {exc.code}: {_http_detail(exc)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{api_name} connection error: {exc.reason}") from exc


def discover_trend() -> str:
    query = os.getenv("OPENPILOT_TREND_QUERY", "trending vietnam")
    key = os.getenv("YOUTUBE_API_KEY")
    if key:
        params = urllib.parse.urlencode({"part": "snippet", "q": query, "type": "video", "order": "date", "maxResults": "10", "key": key})
        try:
            data = _get_json(f"https://www.googleapis.com/youtube/v3/search?{params}", "YouTube API")
            items = data.get("items", [])
            if items:
                title = items[0].get("snippet", {}).get("title", "").strip()
                if title:
                    return title
        except RuntimeError as exc:
            print(f"[TREND] YouTube unavailable: {exc}", flush=True)

    params = urllib.parse.urlencode({"q": query, "hl": "vi", "gl": "VN", "ceid": "VN:vi"})
    request = urllib.request.Request(f"https://news.google.com/rss/search?{params}", headers={"User-Agent": "OpenPilot-Studio/0.7"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            root = ET.fromstring(response.read())
        item = root.find("./channel/item/title")
        title = (item.text or "").strip() if item is not None else ""
        if title:
            return title
    except (urllib.error.URLError, ET.ParseError) as exc:
        print(f"[TREND] News unavailable: {exc}", flush=True)
    fallback = os.getenv("OPENPILOT_TREND_FALLBACK", "Cùng Việt Nam tiến bước")
    print(f"[TREND] Using local fallback topic: {fallback}", flush=True)
    return fallback


def _has_audio(path: Path) -> bool:
    result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=False, timeout=20)
    return result.returncode == 0 and bool(result.stdout.strip())


def _translate_transcript(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    translations = translate_segments([s.text for s in segments])
    clean: list[TranscriptSegment] = []
    for segment, text in zip(segments, translations):
        text = " ".join(text.split()).strip()
        if text:
            segment.vietnamese = text
            clean.append(segment)
    if not clean:
        raise RuntimeError("AI translation produced no usable Vietnamese speech.")
    return clean


def _split_narration(text: str) -> list[str]:
    """Split narration into short subtitle phrases with natural punctuation boundaries."""
    clean = " ".join(text.split())
    if not clean:
        return []
    sentences = [part.strip() for part in re.split(r"(?<=[.!?…])\s+", clean) if part.strip()]
    parts: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        current: list[str] = []
        for word in words:
            candidate = " ".join(current + [word])
            if current and len(candidate) > 48:
                parts.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            parts.append(" ".join(current))
    return parts or [clean]


def _segments_from_script(text: str, duration: float | None) -> list[TranscriptSegment]:
    chunks = _split_narration(text)
    if not chunks:
        return []
    total = max(float(duration or 5.0), 5.0)
    weights = [max(1, len(x.split())) for x in chunks]
    weight_total = sum(weights)
    cursor = 0.0
    result: list[TranscriptSegment] = []
    for index, chunk in enumerate(chunks):
        span = total * weights[index] / weight_total
        end = total if index == len(chunks) - 1 else min(total, cursor + span)
        segment = TranscriptSegment(cursor, end, chunk)
        segment.vietnamese = chunk
        result.append(segment)
        cursor = end
    return result


def _build_narration(segments: list[TranscriptSegment], trend: str, duration: float) -> tuple[str, list[TranscriptSegment]]:
    source = " ".join(s.vietnamese or s.text for s in segments).strip() or trend
    narration = generate_narration(source, duration)
    timed = _segments_from_script(narration, duration)
    if not timed:
        raise RuntimeError("AI narration produced no usable speech.")
    return narration, timed


def _process_one(ui: AutoUI, index: int, trend: str, source: Path, source_url: str, out: Path, whisper_model: str, publish_mode: str) -> dict:
    ui.video_header(index, source.name)
    started = time.perf_counter()
    try:
        source_info = validate_video(source, min_seconds=10.0)
        ui.item("INFO", f"Source {source_info.width}x{source_info.height} | {source_info.duration:.1f}s")

        stage_started = time.perf_counter()
        if _has_audio(source):
            source_segments = _translate_transcript(transcribe(source, whisper_model))
        else:
            source_segments = _segments_from_script(trend, source_info.duration)
        narration, narration_segments = _build_narration(source_segments, trend, source_info.duration or 10.0)
        package = generate_package(narration)
        ui.video_stage(1, "Whisper + AI editorial narration", stage_started)
        ui.item("INFO", f"Narration: {len(narration.split())} words | covers {source_info.duration:.1f}s")

        stem = f"video-{index:02d}-{source.stem}"
        stage_started = time.perf_counter()
        subtitle = write_srt(narration_segments, out / f"{stem}.vi.srt")
        ui.video_stage(2, "Full-video Vietnamese subtitles", stage_started)

        title = str(package.get("title") or trend).strip()
        hashtags = package.get("hashtags", [])
        hashtag_text = " ".join(hashtags) if isinstance(hashtags, list) else str(hashtags)

        stage_started = time.perf_counter()
        voice = synthesize_speech(narration, out / f"{stem}.vi.mp3")
        ui.video_stage(3, "Professional Vietnamese narration / TTS", stage_started)

        stage_started = time.perf_counter()
        final_video = render_final(source, subtitle, voice, out / f"{stem}.final.mp4")
        final_info = validate_video(final_video, min_seconds=10.0, require_audio=True)
        ui.video_stage(4, "FFmpeg 9:16 + narration + subtitles", stage_started)

        stage_started = time.perf_counter()
        published = "not_requested"
        status = "ready_for_publish"
        if publish_mode == "tiktok":
            published = publish_tiktok(str(final_video), f"{title} {hashtag_text}".strip()); status = "published"
        elif publish_mode == "youtube":
            published = publish_youtube(str(final_video), title, f"{package.get('description', '')}\n\n{hashtag_text}"); status = "published"
        ui.video_stage(5, "Official publishing", stage_started)

        elapsed = time.perf_counter() - started
        ui.item("OK", f"Completed in {elapsed:.1f}s | {final_info.width}x{final_info.height} | {final_info.duration:.1f}s")
        ui.item("->", f"Video : {final_video}")
        ui.item("->", f"Title : {title}")
        ui.item("->", f"Tags  : {hashtag_text}")
        return {"index": index, "source": "douyin", "source_url": source_url, "input_video": str(source), "subtitle_file": str(subtitle), "output_video": str(final_video), "duration_seconds": round(final_info.duration or 0, 2), "narration_words": len(narration.split()), "title": title, "hashtags": hashtag_text, "status": status, "published": published, "error": "", "elapsed_seconds": round(elapsed, 2)}
    except Exception as exc:
        elapsed = time.perf_counter() - started
        ui.item("ERR", f"Failed after {elapsed:.1f}s: {exc}")
        return {"index": index, "source": "douyin", "source_url": source_url, "input_video": str(source), "subtitle_file": "", "output_video": "", "duration_seconds": 0, "narration_words": 0, "title": "", "hashtags": "", "status": "failed", "published": "not_requested", "error": str(exc), "elapsed_seconds": round(elapsed, 2)}


def run_auto(output_dir: str = "output", whisper_model: str = "small") -> AutoResult:
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    target = max(1, min(50, int(os.getenv("OPENPILOT_BATCH_SIZE", "10"))))
    ui = AutoUI(target); ui.header()

    ui.phase(1, "TREND DISCOVERY", "Finding a current topic for the Douyin search")
    trend = discover_trend(); ui.item("OK", f"Trend: {trend}")
    ui.phase(2, "DOUYIN ACQUISITION", f"Searching for {target} videos | strict duration >10s")
    videos = acquire_douyin_batch(trend, out / "source" / "douyin", target)
    ui.item("OK", f"Downloaded {len(videos)}/{target} Douyin videos")

    publish_mode = os.getenv("OPENPILOT_PUBLISH", "none").lower()
    if publish_mode not in {"none", "tiktok", "youtube"}:
        raise RuntimeError("OPENPILOT_PUBLISH must be none, tiktok, or youtube.")

    ui.phase(3, "CONTENT PROCESSING", "Whisper -> editorial narration -> full-video subtitles -> TTS -> final MP4")
    results = [_process_one(ui, i, trend, source, url, out, whisper_model, publish_mode) for i, (source, url) in enumerate(videos, 1)]
    success = sum(r["status"] in {"ready_for_publish", "published"} for r in results)
    failed = len(results) - success
    manifest_path = out / "auto-manifest.json"
    manifest_path.write_text(json.dumps({"version": "0.9", "trend": trend, "source_policy": "douyin_only", "minimum_duration_exclusive_seconds": 10, "narration": {"enabled": True, "style": "modern_professional_full_video", "target_words_per_second": 2.05, "subtitle_style": "compact_two_line_34_char_max"}, "requested": target, "acquired": len(videos), "completed": success, "failed": failed, "publish_mode": publish_mode, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")

    ui.phase(8, "FINAL REPORT", "Batch processing finished"); ui.finish(success, failed)
    first = next((r for r in results if r["status"] != "failed"), results[0] if results else {})
    status = "published" if publish_mode != "none" and success else ("ready_for_publish" if success else "failed")
    return AutoResult(trend, first.get("source_url", ""), first.get("input_video", ""), first.get("subtitle_file", ""), first.get("output_video", ""), status, first.get("title", ""), first.get("hashtags", ""), f"Completed {success}/{len(videos)} Douyin videos. Manifest: {manifest_path}", first.get("published", "not_requested"), results)
