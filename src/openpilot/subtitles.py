from __future__ import annotations

from pathlib import Path


def _stamp(seconds: float) -> str:
    total_ms = max(0, int(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for i, seg in enumerate(segments, 1):
        text = getattr(seg, "vietnamese", getattr(seg, "text", ""))
        lines += [str(i), f"{_stamp(seg.start)} --> {_stamp(seg.end)}", text, ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
