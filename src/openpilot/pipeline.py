from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .media import make_vertical
from .subtitles import write_srt
from .transcription import transcribe


@dataclass
class PipelineResult:
    input_video: str
    subtitle_file: str
    output_video: str
    segments: int


def process_video(input_video: str | Path, output_dir: str | Path = "output", whisper_model: str = "small") -> PipelineResult:
    """Build a social-ready Vietnamese-video pipeline from a user-owned source video.

    The translation provider is intentionally injected later; this first release keeps
    source text unchanged so users can plug in their preferred LLM/translation service.
    """
    source = Path(input_video)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    segments = transcribe(source, whisper_model)
    srt = write_srt(segments, out / f"{source.stem}.vi.srt")
    rendered = make_vertical(source, out / f"{source.stem}.vertical.mp4")
    result = PipelineResult(str(source), str(srt), str(rendered), len(segments))
    (out / f"{source.stem}.json").write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return result
