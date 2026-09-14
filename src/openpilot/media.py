from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class MediaError(RuntimeError):
    pass


@dataclass
class MediaInfo:
    duration: float | None
    width: int | None
    height: int | None


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise MediaError("FFmpeg is required. Install FFmpeg and add it to PATH.")


def probe(path: str | Path) -> MediaInfo:
    require_ffmpeg()
    p = Path(path)
    if not p.exists():
        raise MediaError(f"Video not found: {p}")
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "json", str(p)]
    if shutil.which("ffprobe") is None:
        raise MediaError("ffprobe is required. Install FFmpeg and add it to PATH.")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise MediaError(result.stderr.strip() or "Unable to inspect video")
    data = json.loads(result.stdout or "{}")
    stream = next((s for s in data.get("streams", []) if s.get("width")), {})
    duration = data.get("format", {}).get("duration")
    return MediaInfo(float(duration) if duration else None, stream.get("width"), stream.get("height"))


def make_vertical(input_path: str | Path, output_path: str | Path) -> Path:
    """Create a 9:16 social-ready render without cropping the important center."""
    require_ffmpeg()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "192k", str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise MediaError(result.stderr.strip()[-2000:] or "FFmpeg render failed")
    return out
