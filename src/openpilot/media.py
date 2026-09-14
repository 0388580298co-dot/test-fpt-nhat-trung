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
    video_codec: str | None = None
    audio_codec: str | None = None
    pixel_format: str | None = None


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise MediaError("FFmpeg + ffprobe are required. Install FFmpeg and add them to PATH.")


def _run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"FFmpeg operation timed out after {timeout}s") from exc


def probe(path: str | Path) -> MediaInfo:
    require_ffmpeg()
    p = Path(path)
    if not p.exists() or p.stat().st_size < 100_000:
        raise MediaError(f"Media file is missing or too small: {p}")
    result = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=index,width,height,codec_name,codec_type,profile,pix_fmt,level", "-of", "json", str(p)], 30)
    if result.returncode != 0:
        raise MediaError(result.stderr.strip() or f"Unable to inspect media: {p}")
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise MediaError("ffprobe returned invalid JSON") from exc
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    duration = data.get("format", {}).get("duration")
    return MediaInfo(float(duration) if duration not in (None, "") else None, video.get("width"), video.get("height"), video.get("codec_name"), audio.get("codec_name"), video.get("pix_fmt"))


def validate_video(path: str | Path, *, min_seconds: float = 0.0, require_audio: bool = False) -> MediaInfo:
    info = probe(path)
    if not info.duration or info.duration < min_seconds:
        raise MediaError(f"Video duration {info.duration or 0:.2f}s is below required {min_seconds:.2f}s: {path}")
    if not info.width or not info.height or info.video_codec not in {"h264", "hevc", "vp9", "av1", "mpeg4"}:
        raise MediaError(f"Video stream is not usable: {path}")
    if require_audio and not info.audio_codec:
        raise MediaError(f"Audio stream is missing: {path}")
    return info


def _atomic_replace(temp: Path, output: Path) -> None:
    if not temp.exists() or temp.stat().st_size < 100_000:
        raise MediaError(f"FFmpeg did not produce a usable output: {output}")
    temp.replace(output)


def _subtitle_filter(srt: Path) -> str:
    value = str(srt.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    return f"subtitles='{value}':force_style='FontName=Arial,FontSize=18,Outline=2,Shadow=1,MarginV=120,Alignment=2'"


def _atempo_chain(factor: float) -> str:
    # FFmpeg's atempo accepts 0.5-2.0. Split extreme values into safe stages.
    factor = max(0.5, min(2.0, factor))
    return ",".join([f"atempo={factor:.6f}"])


def fit_audio_to_duration(voice_path: str | Path, target_seconds: float) -> Path:
    """Gently time-stretch/compress narration so speech spans the video instead of ending early."""
    require_ffmpeg()
    voice = Path(voice_path)
    if not voice.exists() or voice.stat().st_size < 1024:
        raise MediaError(f"Voice file not found or empty: {voice}")
    target = max(1.0, float(target_seconds))
    info = probe(voice)
    if not info.duration or info.duration <= 0:
        raise MediaError(f"Unable to determine narration duration: {voice}")
    ratio = info.duration / target
    # Keep the delivery natural. The AI script is already targeted to the video,
    # so only a moderate correction should normally be necessary.
    if 0.88 <= ratio <= 1.12:
        return voice
    adjusted = voice.with_suffix(voice.suffix + ".fit.m4a")
    adjusted.unlink(missing_ok=True)
    factor = max(0.70, min(1.35, ratio))
    cmd = [
        "ffmpeg", "-y", "-i", str(voice), "-vn", "-af", _atempo_chain(factor),
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", str(adjusted),
    ]
    result = _run(cmd, 180)
    if result.returncode != 0 or not adjusted.exists() or adjusted.stat().st_size < 1024:
        adjusted.unlink(missing_ok=True)
        raise MediaError(result.stderr.strip()[-3000:] or "Unable to fit narration duration")
    return adjusted


def render_final(input_path: str | Path, subtitle_path: str | Path, voice_path: str | Path, output_path: str | Path) -> Path:
    """Render a validated 1080x1920 H.264/AAC MP4 with full-video Vietnamese narration."""
    require_ffmpeg()
    source, srt, voice, output = Path(input_path), Path(subtitle_path), Path(voice_path), Path(output_path)
    if not source.exists(): raise MediaError(f"Source video not found: {source}")
    if not srt.exists(): raise MediaError(f"Subtitle file not found: {srt}")
    if not voice.exists() or voice.stat().st_size < 1024: raise MediaError(f"Voice file not found or empty: {voice}")
    source_info = validate_video(source)
    if not source_info.duration: raise MediaError("Source duration is unavailable")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".rendering.mp4")
    fitted_voice = fit_audio_to_duration(voice, source_info.duration)
    vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1," + _subtitle_filter(srt)
    cmd = [
        "ffmpeg", "-y", "-i", str(source), "-i", str(fitted_voice),
        "-map", "0:v:0", "-map", "1:a:0", "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "main", "-level:v", "4.0", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-af", "apad", "-t", f"{source_info.duration:.3f}",
        "-movflags", "+faststart", str(temp),
    ]
    try:
        result = _run(cmd, 300)
        if result.returncode != 0: raise MediaError(result.stderr.strip()[-3000:] or "FFmpeg final render failed")
        info = probe(temp)
        if info.width != 1080 or info.height != 1920 or info.video_codec != "h264" or info.audio_codec != "aac" or info.pixel_format != "yuv420p":
            raise MediaError(f"Final validation failed: {info.width}x{info.height}, video={info.video_codec}, audio={info.audio_codec}, pix_fmt={info.pixel_format}")
        _atomic_replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)
        if fitted_voice != voice:
            fitted_voice.unlink(missing_ok=True)
    return output


def make_vertical(input_path: str | Path, output_path: str | Path) -> Path:
    """Backward-compatible video-only 9:16 renderer."""
    require_ffmpeg()
    source, out = Path(input_path), Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix(out.suffix + ".rendering.mp4")
    vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    cmd = ["ffmpeg", "-y", "-i", str(source), "-map", "0:v:0", "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "main", "-level:v", "4.0", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(temp)]
    try:
        result = _run(cmd, 300)
        if result.returncode != 0: raise MediaError(result.stderr.strip()[-3000:] or "FFmpeg render failed")
        validate_video(temp); _atomic_replace(temp, out)
    finally:
        temp.unlink(missing_ok=True)
    return out
