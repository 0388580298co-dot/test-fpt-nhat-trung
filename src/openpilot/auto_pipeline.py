from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .pipeline import process_video


@dataclass
class AutoResult:
    trend: str
    source_url: str
    input_video: str
    subtitle_file: str
    output_video: str
    status: str
    message: str = ""


def _get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(url, headers=headers or {"User-Agent": "OpenPilot-Studio/0.4"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def discover_trend() -> str:
    """Find one recent trend query through the official YouTube Data API."""
    key = os.getenv("YOUTUBE_API_KEY")
    query = os.getenv("OPENPILOT_TREND_QUERY", "trending vietnam")
    if not key:
        raise RuntimeError("Missing YOUTUBE_API_KEY. Add an official YouTube Data API key first.")
    params = urllib.parse.urlencode({
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "date",
        "maxResults": "10",
        "key": key,
    })
    data = _get_json(f"https://www.googleapis.com/youtube/v3/search?{params}")
    items = data.get("items", [])
    if not items:
        raise RuntimeError("Trend Engine found no recent videos for the configured query.")
    return items[0].get("snippet", {}).get("title", query)


def acquire_video(query: str, output_dir: Path) -> tuple[Path, str]:
    """Acquire a video from Pexels' authorized API; never bypasses platform controls."""
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("Missing PEXELS_API_KEY. Configure a permitted video source before auto mode.")
    params = urllib.parse.urlencode({"query": query, "per_page": "10", "orientation": "portrait"})
    data = _get_json(
        f"https://api.pexels.com/videos/search?{params}",
        headers={"Authorization": key, "User-Agent": "OpenPilot-Studio/0.4"},
    )
    videos = data.get("videos", [])
    for item in videos:
        for file_info in item.get("video_files", []):
            link = file_info.get("link")
            if link and file_info.get("width", 0) >= 720:
                output_dir.mkdir(parents=True, exist_ok=True)
                target = output_dir / f"source-{item['id']}.mp4"
                request = urllib.request.Request(link, headers={"User-Agent": "OpenPilot-Studio/0.4"})
                with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as stream:
                    stream.write(response.read())
                return target, link
    raise RuntimeError("The permitted video source returned no usable video.")


def run_auto(output_dir: str = "output", whisper_model: str = "small") -> AutoResult:
    """Run the no-manual-input acquisition and media pipeline.

    Publishing is intentionally not performed here until an official publisher is
    configured and the user has authorized it. This prevents accidental uploads.
    """
    out = Path(output_dir)
    trend = discover_trend()
    source, source_url = acquire_video(trend, out / "source")
    result = process_video(str(source), str(out), whisper_model)
    return AutoResult(
        trend=trend,
        source_url=source_url,
        input_video=result.input_video,
        subtitle_file=result.subtitle_file,
        output_video=result.output_video,
        status="ready_for_publish",
        message="Content was discovered and processed automatically. Configure an official publisher to upload it.",
    )
