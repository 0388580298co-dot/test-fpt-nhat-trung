from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


def _float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        return max(minimum, min(maximum, float(os.getenv(name, str(default)))))
    except ValueError:
        return default


@dataclass(frozen=True)
class AutoConfig:
    batch_size: int = _int_env("OPENPILOT_BATCH_SIZE", 10, 1, 50)
    min_video_seconds: float = _float_env("OPENPILOT_MIN_VIDEO_SECONDS", 10.0, 1.0, 3600.0)
    browser_timeout_ms: int = _int_env("OPENPILOT_BROWSER_TIMEOUT_MS", 20_000, 10_000, 90_000)
    browser_settle_ms: int = _int_env("OPENPILOT_BROWSER_SETTLE_MS", 2_000, 500, 10_000)
    download_timeout_s: int = _int_env("OPENPILOT_DOWNLOAD_TIMEOUT", 45, 10, 180)
    max_browser_media: int = _int_env("OPENPILOT_MAX_BROWSER_MEDIA", 5, 1, 12)
    ai_timeout_s: int = _int_env("OPENPILOT_AI_TIMEOUT", 180, 30, 600)
    whisper_model: str = os.getenv("OPENPILOT_WHISPER_MODEL", "small")


CONFIG = AutoConfig()
