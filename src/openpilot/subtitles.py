from __future__ import annotations

import re
from pathlib import Path


def _stamp(seconds: float) -> str:
    total_ms = max(0, int(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _subtitle_text(value: object, max_chars: int = 46) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    # Two visual lines are easier to read on a 9:16 phone screen.
    if len(lines) <= 2:
        return "\n".join(lines)
    half = (len(lines) + 1) // 2
    return "\n".join((" ".join(lines[:half]), " ".join(lines[half:])))


def write_srt(segments, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    number = 0
    for seg in segments:
        text = _subtitle_text(getattr(seg, "vietnamese", getattr(seg, "text", "")))
        if not text:
            continue
        start = max(0.0, float(seg.start))
        end = max(start + 0.25, float(seg.end))
        number += 1
        lines += [str(number), f"{_stamp(start)} --> {_stamp(end)}", text, ""]
    if not number:
        raise RuntimeError("Cannot create subtitles: no usable Vietnamese segments.")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
