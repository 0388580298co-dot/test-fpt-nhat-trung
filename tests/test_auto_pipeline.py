from pathlib import Path

import pytest

from openpilot.auto_pipeline import acquire_video, discover_trend


def test_discover_trend_requires_youtube_key(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="YOUTUBE_API_KEY"):
        discover_trend()


def test_acquire_video_requires_pexels_key(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="PEXELS_API_KEY"):
        acquire_video("test", tmp_path)
