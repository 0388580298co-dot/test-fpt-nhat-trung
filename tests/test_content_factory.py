from pathlib import Path

from openpilot.publishers import ManualPublisher
from openpilot.subtitles import write_srt
from openpilot.translation import SimpleTranslator, translate_segments
from openpilot.trends import ManualTrendSource, TrendCandidate


def test_srt_writer(tmp_path: Path):
    class Segment:
        start = 0.0
        end = 2.5
        text = "Hello"

    path = write_srt([Segment()], tmp_path / "x.srt")
    assert "00:00:00,000 --> 00:00:02,500" in path.read_text(encoding="utf-8")


def test_translation_interface():
    class Segment:
        text = "Xin chao"

    result = translate_segments([Segment()], SimpleTranslator())
    assert result[0].vietnamese == "Xin chao"


def test_trend_source_sorts_by_score():
    source = ManualTrendSource([
        TrendCandidate("low", "u1", "douyin", 50),
        TrendCandidate("high", "u2", "douyin", 90),
    ])
    assert source.trending(1)[0].title == "high"


def test_publisher_is_dry_run():
    result = ManualPublisher("youtube_shorts").publish("video.mp4", "Demo")
    assert result.status == "dry_run"
