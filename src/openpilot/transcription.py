from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


def transcribe(video_path: str | Path, model: str = "small") -> list[TranscriptSegment]:
    """Transcribe speech with faster-whisper and provide a useful media error."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Install optional speech dependencies: pip install -e '.[media]'") from exc

    source = Path(video_path)
    if not source.exists():
        raise RuntimeError(f"Input video does not exist: {source}")

    engine = WhisperModel(model, compute_type="int8")
    try:
        segments, _ = engine.transcribe(str(source), vad_filter=True)
        return [TranscriptSegment(float(s.start), float(s.end), s.text.strip()) for s in segments if s.text.strip()]
    except IndexError as exc:
        raise RuntimeError(
            f"Whisper could not decode an audio stream from '{source}'. "
            "The downloaded video may contain no usable audio track."
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Whisper could not decode '{source}': {exc}") from exc
