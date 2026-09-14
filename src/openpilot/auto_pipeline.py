from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .ai_content import generate_package, synthesize_speech, translate_segments
from .douyin_source import acquire_douyin_batch
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
    results: list[dict] = field(default_factory=list)


class AutoUI:
    """Professional, dependency-free terminal UI for AUTO runs."""

    def __init__(self, total: int):
        self.total = total
        self.started = time.perf_counter()

    @staticmethod
    def line(char: str = "=", width: int = 76) -> None:
        print(char * width, flush=True)

    def header(self) -> None:
        self.line("=")
        print("  OPENPILOT STUDIO  |  AI CONTENT FACTORY", flush=True)
        print("  AUTOMATIC DOUYIN -> VIETNAMESE -> 9:16 VIDEO", flush=True)
        self.line("=")
        print(f"  Batch size : {self.total:02d} videos", flush=True)
        print(f"  AI         : {os.getenv('OPENPILOT_AI_PROVIDER', 'local')}", flush=True)
        print(f"  TTS        : {os.getenv('OPENPILOT_TTS_PROVIDER', 'piper')}", flush=True)
        print(f"  Publish    : {os.getenv('OPENPILOT_PUBLISH', 'none')}", flush=True)
        self.line("-")

    def phase(self, number: int, title: str, detail: str = "") -> None:
        print(f"\n  [{number}/8] {title}", flush=True)
        if detail:
            print(f"        {detail}", flush=True)

    def item(self, icon: str, message: str) -> None:
        print(f"        {icon} {message}", flush=True)

    def video_header(self, index: int, name: str) -> None:
        print(f"\n  +---------------- VIDEO {index:02d}/{self.total:02d} ----------------+", flush=True)
        print(f"  | {name[:60]}", flush=True)
        print("  +--------------------------------------------------+", flush=True)

    def video_stage(self, stage: int, name: str, started: float) -> None:
        elapsed = time.perf_counter() - started
        print(f"        [{stage}/5] {name:<34} {elapsed:6.1f}s", flush=True)

    def finish(self, success: int, failed: int) -> None:
        elapsed = time.perf_counter() - self.started
        self.line("-")
        print("  RUN SUMMARY", flush=True)
        print(f"  Completed : {success:02d}/{self.total:02d}", flush=True)
        print(f"  Failed    : {failed:02d}/{self.total:02d}", flush=True)
        print(f"  Elapsed   : {elapsed:.1f}s", flush=True)
        print(f"  Manifest  : output\\auto-manifest.json", flush=True)
        self.line("=")


def _http_detail(exc: urllib.error.HTTPError) -> str:
    detail = exc.read().decode("utf-8", errors="replace").strip()
    return detail[:600] if detail else str(exc.reason)


def _get_json(url: str, headers: dict[str, str] | None = None, api_name: str = "API") -> dict:
    request = urllib.request.Request(url, headers=headers or {"User-Agent": "OpenPilot-Studio/0.6"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{api_name} {exc.code}: {_http_detail(exc)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{api_name} connection error: {exc.reason}") from exc


def _discover_trend_from_news(query: str) -> str:
    params = urllib.parse.urlencode({"q": query, "hl": "vi", "gl": "VN", "ceid": "VN:vi"})
    request = urllib.request.Request(
        f"https://news.google.com/rss/search?{params}",
        headers={"User-Agent": "OpenPilot-Studio/0.6"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            root = ET.fromstring(response.read())
    except (urllib.error.URLError, ET.ParseError) as exc:
        raise RuntimeError(f"Free trend discovery failed: {exc}") from exc
    item = root.find("./channel/item/title")
    title = (item.text or "").strip() if item is not None else ""
    if not title:
        raise RuntimeError("Free trend discovery returned no recent topic.")
    return title


def discover_trend() -> str:
    query = os.getenv("OPENPILOT_TREND_QUERY", "trending vietnam")
    key = os.getenv("YOUTUBE_API_KEY")

    # 1) Prefer YouTube search when an API key is configured.
    if key:
        params = urllib.parse.urlencode({"part": "snippet", "q": query, "type": "video", "order": "date", "maxResults": "10", "key": key})
        try:
            data = _get_json(f"https://www.googleapis.com/youtube/v3/search?{params}", api_name="YouTube API")
            items = data.get("items", [])
            if items:
                title = items[0].get("snippet", {}).get("title", "").strip()
                if title:
                    return title
        except RuntimeError as exc:
            print(f"[TREND] YouTube unavailable: {exc}", flush=True)

    # 2) Free RSS discovery. Network/DNS failure must not abort AUTO.
    try:
        return _discover_trend_from_news(query)
    except RuntimeError as exc:
        print(f"[TREND] News unavailable: {exc}", flush=True)

    # 3) Deterministic local fallback. This keeps the pipeline running when
    # the PC has no DNS/internet access to the trend provider. The actual
    # Douyin search still runs against this topic and reports the query.
    fallback = os.getenv("OPENPILOT_TREND_FALLBACK", "Cùng Việt Nam tiến bước")
    print(f"[TREND] Using local fallback topic: {fallback}", flush=True)
    return fallback


def _has_audio(path: Path) -> bool:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


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
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video), "-i", str(voice),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest", str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output


def _process_one(ui: AutoUI, index: int, trend: str, source: Path, source_url: str, out: Path, whisper_model: str, publish_mode: str) -> dict:
    ui.video_header(index, source.name)
    started = time.perf_counter()
    try:
        stage_started = time.perf_counter()
        has_audio = _has_audio(source)
        if has_audio:
            segments = transcribe(source, whisper_model)
            source_text = " ".join(s.text for s in segments)
            package = generate_package(source_text or trend)
            translated = translate_segments([s.text for s in segments]) if segments else [str(package.get("translation", trend))]
            for seg, vi in zip(segments, translated):
                seg.vietnamese = vi
        else:
            package = generate_package(trend)
            narration = str(package.get("translation") or trend).strip()
            segments = _segments_from_script(narration, probe(source).duration)
            for seg in segments:
                seg.vietnamese = seg.text
        ui.video_stage(1, "Whisper + AI translation", stage_started)

        stem = f"video-{index:02d}-{source.stem}"
        stage_started = time.perf_counter()
        subtitle = write_srt(segments, out / f"{stem}.vi.srt")
        ui.video_stage(2, "Vietnamese subtitles (SRT)", stage_started)

        title = str(package.get("title") or trend).strip()
        hashtags = package.get("hashtags", [])
        hashtag_text = " ".join(hashtags) if isinstance(hashtags, list) else str(hashtags)
        narration_text = " ".join(getattr(s, "vietnamese", s.text) for s in segments).strip() or str(package.get("translation") or trend).strip()

        stage_started = time.perf_counter()
        voice = synthesize_speech(narration_text, out / f"{stem}.vi.mp3")
        ui.video_stage(3, "Vietnamese voice / TTS", stage_started)

        stage_started = time.perf_counter()
        vertical = make_vertical(source, out / f"{stem}.vertical.mp4")
        voiced = _mux_voice(Path(vertical), voice, out / f"{stem}.final.mp4")
        ui.video_stage(4, "FFmpeg render 9:16 + audio", stage_started)

        stage_started = time.perf_counter()
        published = "not_requested"
        status = "ready_for_publish"
        if publish_mode == "tiktok":
            published = publish_tiktok(str(voiced), f"{title} {hashtag_text}".strip())
            status = "published"
        elif publish_mode == "youtube":
            published = publish_youtube(str(voiced), title, f"{package.get('description', '')}\n\n{hashtag_text}")
            status = "published"
        ui.video_stage(5, "Official publishing", stage_started)

        total_time = time.perf_counter() - started
        ui.item("OK", f"Hoan tat trong {total_time:.1f}s")
        ui.item("->", f"Video : {voiced}")
        ui.item("->", f"Title : {title}")
        ui.item("->", f"Tags  : {hashtag_text}")
        return {
            "index": index,
            "source": "douyin",
            "source_url": source_url,
            "input_video": str(source),
            "subtitle_file": str(subtitle),
            "output_video": str(voiced),
            "title": title,
            "hashtags": hashtag_text,
            "status": status,
            "published": published,
            "error": "",
            "elapsed_seconds": round(total_time, 2),
        }
    except Exception as exc:
        total_time = time.perf_counter() - started
        ui.item("ERR", f"Loi sau {total_time:.1f}s: {exc}")
        return {
            "index": index,
            "source": "douyin",
            "source_url": source_url,
            "input_video": str(source),
            "subtitle_file": "",
            "output_video": "",
            "title": "",
            "hashtags": "",
            "status": "failed",
            "published": "not_requested",
            "error": str(exc),
            "elapsed_seconds": round(total_time, 2),
        }


def run_auto(output_dir: str = "output", whisper_model: str = "small") -> AutoResult:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    target_count = max(1, min(50, int(os.getenv("OPENPILOT_BATCH_SIZE", "10"))))
    ui = AutoUI(target_count)
    ui.header()

    ui.phase(1, "TREND DISCOVERY", "Finding a current topic for the Douyin search")
    trend = discover_trend()
    ui.item("OK", f"Trend: {trend}")

    ui.phase(2, "DOUYIN ACQUISITION", f"Searching and downloading {target_count} Douyin videos")
    videos = acquire_douyin_batch(trend, out / "source" / "douyin", limit=target_count)
    ui.item("OK", f"Downloaded {len(videos)}/{target_count} Douyin videos")
    if len(videos) < target_count:
        ui.item("WARN", f"Only {len(videos)} accessible Douyin videos were found; no fallback source is used.")

    publish_mode = os.getenv("OPENPILOT_PUBLISH", "none").lower()
    if publish_mode not in {"none", "tiktok", "youtube"}:
        raise RuntimeError("OPENPILOT_PUBLISH must be none, tiktok, or youtube.")

    ui.phase(3, "CONTENT PROCESSING", "Each downloaded video is processed independently")
    results: list[dict] = []
    for index, (source, source_url) in enumerate(videos, 1):
        result = _process_one(ui, index, trend, source, source_url, out, whisper_model, publish_mode)
        results.append(result)

    success_count = sum(item["status"] in {"ready_for_publish", "published"} for item in results)
    failed_count = len(results) - success_count
    manifest = {
        "trend": trend,
        "source_policy": "douyin_only",
        "requested": target_count,
        "acquired": len(videos),
        "completed": success_count,
        "failed": failed_count,
        "publish_mode": publish_mode,
        "results": results,
    }
    manifest_path = out / "auto-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    ui.phase(8, "FINAL REPORT", "Batch processing finished")
    ui.finish(success_count, failed_count)

    first = next((r for r in results if r["status"] != "failed"), results[0] if results else {})
    status = "published" if publish_mode != "none" and success_count else ("ready_for_publish" if success_count else "failed")
    message = f"Completed {success_count}/{len(videos)} Douyin videos. Manifest: {manifest_path}"
    return AutoResult(
        trend=trend,
        source_url=first.get("source_url", ""),
        input_video=first.get("input_video", ""),
        subtitle_file=first.get("subtitle_file", ""),
        output_video=first.get("output_video", ""),
        status=status,
        title=first.get("title", ""),
        hashtags=first.get("hashtags", ""),
        message=message,
        published=first.get("published", "not_requested"),
        results=results,
    )
