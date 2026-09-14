from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .ai_content import synthesize_speech, translate_segments
from .media import render_final, validate_video
from .subtitles import write_srt
from .transcription import transcribe


@dataclass
class PipelineResult:
    input_video: str
    subtitle_file: str
    voice_file: str
    output_video: str
    segments: int
    duration_seconds: float


def process_video(input_video: str | Path, output_dir: str | Path = "output", whisper_model: str = "small") -> PipelineResult:
    """Process a local video through the same production path used by AUTO."""
    source = Path(input_video)
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    info = validate_video(source)
    segments = transcribe(source, whisper_model)
    translations = translate_segments([segment.text for segment in segments])
    usable = []
    for segment, text in zip(segments, translations):
        text = " ".join(text.split()).strip()
        if text:
            segment.vietnamese = text
            usable.append(segment)
    if not usable:
        raise RuntimeError("AI translation produced no usable Vietnamese speech.")
    srt = write_srt(usable, out / f"{source.stem}.vi.srt")
    voice = synthesize_speech(" ".join(s.vietnamese for s in usable), out / f"{source.stem}.vi.mp3")
    rendered = render_final(source, srt, voice, out / f"{source.stem}.final.mp4")
    final_info = validate_video(rendered, require_audio=True)
    result = PipelineResult(str(source), str(srt), str(voice), str(rendered), len(usable), final_info.duration or info.duration or 0.0)
    (out / f"{source.stem}.json").write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return result
