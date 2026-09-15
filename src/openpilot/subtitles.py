from __future__ import annotations

import re
from pathlib import Path


_STOPS = re.compile(r"(?<=[.!?…])\s+")


def _stamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _clean_text(value: object) -> str:
    text = str(value or "")
    text = text.replace("\u00a0", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?…])", r"\1", text)
    return text


def _balanced_lines(text: str, max_chars: int = 34) -> list[str]:
    """Wrap Vietnamese into at most two compact, visually balanced lines."""
    words = text.split()
    if not words:
        return []

    # Prefer punctuation boundaries first, then fall back to word boundaries.
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

    if len(lines) <= 2:
        return lines

    # Reflow all words into two balanced lines instead of making a third line.
    total = len(words)
    best_index = 1
    best_score = float("inf")
    for index in range(1, total):
        left = " ".join(words[:index])
        right = " ".join(words[index:])
        if len(left) > max_chars or len(right) > max_chars:
            continue
        score = abs(len(left) - len(right))
        # Slightly prefer a punctuation boundary.
        if left[-1:] in ".,;:!?…":
            score -= 8
        if score < best_score:
            best_score = score
            best_index = index

    left = " ".join(words[:best_index])
    right = " ".join(words[best_index:])
    if len(left) <= max_chars and len(right) <= max_chars:
        return [left, right]

    # Extremely long content: keep the first two readable chunks.
    return [" ".join(words[: max(1, total // 2)]), " ".join(words[max(1, total // 2) :])]


def _subtitle_text(value: object, max_chars: int = 34) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    return "\n".join(_balanced_lines(text, max_chars=max_chars)[:2])


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
        end = max(start + 0.45, float(seg.end))
        if end <= start:
            continue
        number += 1
        lines += [str(number), f"{_stamp(start)} --> {_stamp(end)}", text, ""]
    if not number:
        raise RuntimeError("Cannot create subtitles: no usable Vietnamese segments.")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
