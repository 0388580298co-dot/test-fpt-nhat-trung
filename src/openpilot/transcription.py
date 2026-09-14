from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    vietnamese: str = ""


def _extract_clean_audio(source: Path) -> tuple[Path, tempfile.TemporaryDirectory[str]]:
    temp_dir = tempfile.TemporaryDirectory(prefix="openpilot-whisper-")
    wav = Path(temp_dir.name) / "speech.wav"
    filters = "highpass=f=80,lowpass=f=7600,afftdn=nf=-25,dynaudnorm=f=150:g=15,loudnorm=I=-16:TP=-1.5:LRA=11"
    result = subprocess.run([
        "ffmpeg", "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
        "-af", filters, "-c:a", "pcm_s16le", str(wav),
    ], capture_output=True, text=True, check=False, timeout=120)
    if result.returncode != 0 or not wav.exists() or wav.stat().st_size < 1024:
        temp_dir.cleanup()
        detail = (result.stderr or "").strip().splitlines()
        raise RuntimeError("Could not extract a usable speech track for Whisper. " + (detail[-1][:400] if detail else "ffmpeg returned no details."))
    return wav, temp_dir


def _looks_like_hallucination(text: str, compression_ratio: float, avg_logprob: float, no_speech_prob: float) -> bool:
    clean = " ".join(text.split())
    if not clean:
        return True
    if compression_ratio > 2.8 and len(clean) > 20:
        return True
    if no_speech_prob >= 0.72 and avg_logprob < -0.9:
        return True
    words = clean.split()
    if len(words) >= 8 and len({w.casefold() for w in words}) / len(words) < 0.28:
        return True
    return False


def _remove_cross_segment_repeats(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    result: list[TranscriptSegment] = []
    previous = ""
    for segment in segments:
        text = " ".join(segment.text.split()).strip()
        if not text:
            continue
        # Drop an identical/near-identical ASR loop that is repeated across
        # adjacent segments, while keeping legitimate repeated short phrases.
        if previous and len(text) >= 12 and text.casefold() == previous.casefold():
            continue
        segment.text = text
        result.append(segment)
        previous = text
    return result


def transcribe(video_path: str | Path, model: str = "small") -> list[TranscriptSegment]:
    """Whisper transcription tuned for mixed speech/music short-form video."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Install speech dependencies: pip install -e '.[media]'") from exc

    source = Path(video_path)
    if not source.exists():
        raise RuntimeError(f"Input video does not exist: {source}")

    print(f"[WHISPER] Preparing clean speech track: {source.name}", flush=True)
    audio, temp_dir = _extract_clean_audio(source)
    compute_type = os.getenv("OPENPILOT_WHISPER_COMPUTE", "int8")
    engine = WhisperModel(model, compute_type=compute_type)
    try:
        segments, info = engine.transcribe(
            str(audio),
            beam_size=5,
            best_of=5,
            temperature=0.0,
            condition_on_previous_text=False,
            compression_ratio_threshold=2.8,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.65,
            vad_filter=True,
            vad_parameters={
                "threshold": 0.5,
                "min_speech_duration_ms": 250,
                "max_speech_duration_s": 30,
                "min_silence_duration_ms": 500,
                "speech_pad_ms": 180,
            },
        )
        detected = getattr(info, "language", None) or "unknown"
        result: list[TranscriptSegment] = []
        rejected = 0
        for segment in segments:
            text = segment.text.strip()
            if _looks_like_hallucination(
                text,
                float(getattr(segment, "compression_ratio", 0.0) or 0.0),
                float(getattr(segment, "avg_logprob", 0.0) or 0.0),
                float(getattr(segment, "no_speech_prob", 0.0) or 0.0),
            ):
                rejected += 1
                continue
            result.append(TranscriptSegment(float(segment.start), float(segment.end), text))
        result = _remove_cross_segment_repeats(result)
        if rejected:
            print(f"[WHISPER] Rejected {rejected} low-confidence/noise segment(s)", flush=True)
        print(f"[WHISPER] Language={detected} | reliable segments={len(result)}", flush=True)
        if not result:
            raise RuntimeError("Whisper found no reliable speech. The clip may contain mostly music/noise or unclear speech.")
        return result
    except IndexError as exc:
        raise RuntimeError(f"Whisper could not decode '{source}'. The video may have no usable audio stream.") from exc
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"Whisper could not decode '{source}': {exc}") from exc
    finally:
        temp_dir.cleanup()
