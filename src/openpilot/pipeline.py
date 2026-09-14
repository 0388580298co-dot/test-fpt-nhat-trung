from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .ai_content import generate_narration, generate_package, synthesize_speech, translate_segments
from .media import render_final, validate_video
from .subtitles import write_srt
from .transcription import TranscriptSegment, transcribe


@dataclass
class PipelineResult:
    input_video: str
    subtitle_file: str
    voice_file: str
    output_video: str
    segments: int
    duration_seconds: float
    narration_words: int = 0


def _split_narration(text: str) -> list[str]:
    clean = " ".join(text.split())
    parts: list[str] = []
    current = ""
    for token in clean.replace("!", ".").replace("?", ".").replace(";", ".").split("."):
        token = token.strip()
        if not token:
            continue
        current = f"{current} {token}".strip()
        if len(current) >= 55:
            parts.append(current)
            current = ""
    if current:
        parts.append(current)
    return parts or ([clean] if clean else [])


def _timed_narration(text: str, duration: float) -> list[TranscriptSegment]:
    sentences = _split_narration(text)
    if not sentences:
        return []
    weights = [max(1, len(x)) for x in sentences]
    total_weight = sum(weights)
    cursor = 0.0
    result: list[TranscriptSegment] = []
    for index, sentence in enumerate(sentences):
        end = duration if index == len(sentences) - 1 else cursor + duration * weights[index] / total_weight
        segment = TranscriptSegment(cursor, min(duration, end), sentence)
        segment.vietnamese = sentence
        result.append(segment)
        cursor = end
    return result


def process_video(input_video: str | Path, output_dir: str | Path = "output", whisper_model: str = "small") -> PipelineResult:
    """Process a local video with modern Vietnamese narration covering the full duration."""
    source = Path(input_video)
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    info = validate_video(source)

    raw_segments = transcribe(source, whisper_model)
    translations = translate_segments([segment.text for segment in raw_segments])
    source_text = " ".join(text.strip() for text in translations if text.strip()) or "video"
    narration = generate_narration(source_text, info.duration or 10.0)
    segments = _timed_narration(narration, info.duration or 10.0)
    if not segments:
        raise RuntimeError("AI narration produced no usable Vietnamese speech.")

    srt = write_srt(segments, out / f"{source.stem}.vi.srt")
    voice = synthesize_speech(narration, out / f"{source.stem}.vi.mp3")
    rendered = render_final(source, srt, voice, out / f"{source.stem}.final.mp4")
    final_info = validate_video(rendered, require_audio=True)
    result = PipelineResult(str(source), str(srt), str(voice), str(rendered), len(segments), final_info.duration or info.duration or 0.0, len(narration.split()))
    (out / f"{source.stem}.json").write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return result
