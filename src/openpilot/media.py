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
    if shutil.which("ffprobe") is None:
        raise MediaError("ffprobe is required. Install FFmpeg and add it to PATH.")
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration:stream=width,height,codec_name,codec_type,profile,pix_fmt,level",
        "-of", "json", str(p),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)
    if result.returncode != 0:
        raise MediaError(result.stderr.strip() or "Unable to inspect video")
    data = json.loads(result.stdout or "{}")
    stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video" and s.get("width")), {})
    duration = data.get("format", {}).get("duration")
    return MediaInfo(float(duration) if duration else None, stream.get("width"), stream.get("height"))


def _validate_output(path: Path) -> None:
    if not path.exists() or path.stat().st_size < 100_000:
        raise MediaError(f"FFmpeg produced an invalid video file: {path}")
    info = probe(path)
    if not info.duration or not info.width or not info.height:
        raise MediaError(f"FFmpeg produced an incomplete video file: {path}")


def make_vertical(input_path: str | Path, output_path: str | Path) -> Path:
    """Create a Windows-compatible 9:16 H.264 MP4 video track."""
    require_ffmpeg()
    source = Path(input_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix(out.suffix + ".rendering.mp4")
    vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    cmd = [
        "ffmpeg", "-y", "-i", str(source),
        "-map", "0:v:0",
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-profile:v", "main",
        "-level:v", "4.0",
        "-pix_fmt", "yuv420p",
        "-an",
        "-movflags", "+faststart",
        str(temp),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise MediaError(result.stderr.strip()[-2000:] or "FFmpeg render failed")
    try:
        _validate_output(temp)
        temp.replace(out)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
    return out
