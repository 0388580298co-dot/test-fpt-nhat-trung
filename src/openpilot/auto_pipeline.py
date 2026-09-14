from __future__ import annotations

import json
import os
import subprocess
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


def _progress(step: str, message: str) -> None:
    print(f"[{step}] {message}", flush=True)


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
    if not key:
        return _discover_trend_from_news(query)
    params = urllib.parse.urlencode({"part": "snippet", "q": query, "type": "video", "order": "date", "maxResults": "10", "key": key})
    try:
        data = _get_json(f"https://www.googleapis.com/youtube/v3/search?{params}", api_name="YouTube API")
    except RuntimeError:
        return _discover_trend_from_news(query)
    items = data.get("items", [])
    return items[0].get("snippet", {}).get("title", query) if items else _discover_trend_from_news(query)


def _has_audio(path: Path) -> bool:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _download(url: str, target: Path, source_name: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "OpenPilot-Studio/0.6"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response, target.open("wb") as stream:
            stream.write(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{source_name} media {exc.code}: {_http_detail(exc)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{source_name} media connection error: {exc.reason}") from exc
    return target


def _acquire_commons_videos(query: str, output_dir: Path, limit: int) -> list[tuple[Path, str]]:
    terms = [query, "nature landscape", "city street", "people culture"]
    found: list[tuple[Path, str]] = []
    seen_urls: set[str] = set()
    for term in terms:
        params = urllib.parse.urlencode({
            "action": "query", "generator": "search", "gsrsearch": f"{term} filetype:video",
            "gsrnamespace": "6", "gsrlimit": "30", "prop": "imageinfo", "iiprop": "url|mime", "format": "json",
        })
        try:
            data = _get_json(
                f"https://commons.wikimedia.org/w/api.php?{params}",
                headers={"User-Agent": "OpenPilot-Studio/0.6 (local automation)"},
                api_name="Wikimedia Commons API",
            )
        except RuntimeError:
            continue
        for page in data.get("query", {}).get("pages", {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("url")
            mime = str(info.get("mime", "")).lower()
            if not url or url in seen_urls or not (mime.startswith("video/") or url.lower().split("?")[0].endswith((".mp4", ".webm", ".ogv"))):
                continue
            suffix = ".mp4" if "mp4" in mime or url.lower().split("?")[0].endswith(".mp4") else ".webm"
            target = output_dir / f"commons-{page.get('pageid', len(found) + 1)}{suffix}"
            try:
                item = (_download(url, target, "Wikimedia Commons"), url)
            except RuntimeError:
                continue
            seen_urls.add(url)
            found.append(item)
            if len(found) >= limit:
                return found
    return found


def _acquire_pexels_videos(query: str, output_dir: Path, limit: int) -> list[tuple[Path, str]]:
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        return []
    params = urllib.parse.urlencode({"query": query, "per_page": str(max(limit, 10)), "orientation": "portrait"})
    data = _get_json(
        f"https://api.pexels.com/videos/search?{params}",
        headers={"Authorization": key, "User-Agent": "OpenPilot-Studio/0.6"},
        api_name="Pexels API",
    )
    found: list[tuple[Path, str]] = []
    for item in data.get("videos", []):
        files = sorted(item.get("video_files", []), key=lambda x: (x.get("width", 0), x.get("height", 0)), reverse=True)
        for file_info in files:
            link = file_info.get("link")
            if not link or file_info.get("width", 0) < 720:
                continue
            target = output_dir / f"pexels-{item.get('id', len(found) + 1)}.mp4"
            try:
                found.append((_download(link, target, "Pexels"), link))
                break
            except RuntimeError:
                continue
        if len(found) >= limit:
            break
    return found


def acquire_videos(query: str, output_dir: Path, limit: int = 10) -> list[tuple[Path, str]]:
    """Acquire a batch, preferring public Douyin and filling shortages with fallback media."""
    source = os.getenv("OPENPILOT_SOURCE", "auto").lower()
    output_dir.mkdir(parents=True, exist_ok=True)
    videos: list[tuple[Path, str]] = []

    if source in {"douyin", "auto"}:
        try:
            videos = acquire_douyin_batch(query, output_dir / "douyin", limit=limit)
        except RuntimeError as exc:
            if source == "douyin":
                raise
            print(f"[4/8] Douyin không tải đủ: {exc}", flush=True)

    if source in {"auto", "pexels", "fallback"} and len(videos) < limit:
        need = limit - len(videos)
        if os.getenv("PEXELS_API_KEY"):
            try:
                extra = _acquire_pexels_videos(query, output_dir / "pexels", need)
                videos.extend(extra)
            except RuntimeError as exc:
                print(f"[4/8] Pexels không dùng được: {exc}", flush=True)

    if source in {"auto", "commons", "fallback"} and len(videos) < limit:
        need = limit - len(videos)
        print(f"[4/8] Đang bổ sung {need} video từ Wikimedia Commons...", flush=True)
        videos.extend(_acquire_commons_videos(query, output_dir / "commons", need))

    if not videos:
        raise RuntimeError("Không tìm được video nào để xử lý.")
    return videos[:limit]


def acquire_video(query: str, output_dir: Path) -> tuple[Path, str]:
    return acquire_videos(query, output_dir, limit=1)[0]


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
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video), "-i", str(voice), "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(output)
    ], check=True, capture_output=True, text=True)
    return output


def _process_one(index: int, total: int, trend: str, source: Path, source_url: str, out: Path, whisper_model: str, publish_mode: str) -> dict:
    print(f"\n===== VIDEO {index}/{total}: {source.name} =====", flush=True)
    try:
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

        stem = f"video-{index:02d}-{source.stem}"
        subtitle = write_srt(segments, out / f"{stem}.vi.srt")
        title = str(package.get("title") or trend).strip()
        hashtags = package.get("hashtags", [])
        hashtag_text = " ".join(hashtags) if isinstance(hashtags, list) else str(hashtags)
        narration_text = " ".join(getattr(s, "vietnamese", s.text) for s in segments).strip() or str(package.get("translation") or trend).strip()
        voice = synthesize_speech(narration_text, out / f"{stem}.vi.mp3")
        vertical = make_vertical(source, out / f"{stem}.vertical.mp4")
        voiced = _mux_voice(Path(vertical), voice, out / f"{stem}.final.mp4")

        published = "not_requested"
        status = "ready_for_publish"
        if publish_mode == "tiktok":
            published = publish_tiktok(str(voiced), f"{title} {hashtag_text}".strip())
            status = "published"
        elif publish_mode == "youtube":
            published = publish_youtube(str(voiced), title, f"{package.get('description', '')}\n\n{hashtag_text}")
            status = "published"

        return {
            "index": index, "source_url": source_url, "input_video": str(source), "subtitle_file": str(subtitle),
            "output_video": str(voiced), "title": title, "hashtags": hashtag_text,
            "status": status, "published": published, "error": "",
        }
    except Exception as exc:
        print(f"[VIDEO {index}/{total}] LỖI: {exc}", flush=True)
        return {
            "index": index, "source_url": source_url, "input_video": str(source), "subtitle_file": "", "output_video": "",
            "title": "", "hashtags": "", "status": "failed", "published": "not_requested", "error": str(exc),
        }


def run_auto(output_dir: str = "output", whisper_model: str = "small") -> AutoResult:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    target_count = max(1, int(os.getenv("OPENPILOT_BATCH_SIZE", "10")))

    _progress("1/8", "Đang tìm trend...")
    trend = discover_trend()
    _progress("2/8", f"Đang tìm {target_count} video...")
    videos = acquire_videos(trend, out / "source", limit=target_count)
    print(f"[5/8] Đã có {len(videos)}/{target_count} video để xử lý", flush=True)

    publish_mode = os.getenv("OPENPILOT_PUBLISH", "none").lower()
    if publish_mode not in {"none", "tiktok", "youtube"}:
        raise RuntimeError("OPENPILOT_PUBLISH must be none, tiktok, or youtube.")

    results: list[dict] = []
    for index, (source, source_url) in enumerate(videos, 1):
        _progress("6/8", f"Xử lý video {index}/{len(videos)}: Whisper/AI/TTS/9:16")
        result = _process_one(index, len(videos), trend, source, source_url, out, whisper_model, publish_mode)
        results.append(result)

    success_count = sum(item["status"] in {"ready_for_publish", "published"} for item in results)
    failed_count = len(results) - success_count
    manifest = {
        "trend": trend, "requested": target_count, "acquired": len(videos),
        "completed": success_count, "failed": failed_count, "publish_mode": publish_mode, "results": results,
    }
    (out / "auto-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    first = next((r for r in results if r["status"] != "failed"), results[0])
    status = "published" if publish_mode != "none" and success_count else ("ready_for_publish" if success_count else "failed")
    print(f"[8/8] Hoàn tất batch: {success_count}/{len(results)} video thành công; {failed_count} lỗi.", flush=True)
    return AutoResult(
        trend, first["source_url"], first["input_video"], first["subtitle_file"], first["output_video"], status,
        first["title"], first["hashtags"], f"Batch completed: {success_count}/{len(results)} videos succeeded.", first["published"], results,
    )
