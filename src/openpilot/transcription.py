from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


def transcribe(video_path: str | Path, model: str = "small") -> list[TranscriptSegment]:
    """Transcribe speech with faster-whisper. Dependency is optional."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Install optional speech dependencies: pip install -e '.[media]'") from exc

    engine = WhisperModel(model, compute_type="int8")
    segments, _ = engine.transcribe(str(video_path), vad_filter=True)
    return [TranscriptSegment(float(s.start), float(s.end), s.text.strip()) for s in segments if s.text.strip()]
