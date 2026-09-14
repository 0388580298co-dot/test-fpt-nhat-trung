from pathlib import Path

from openpilot.ai_content import _clean_title, _normalize_hashtags
from openpilot.subtitles import write_srt
from openpilot.transcription import TranscriptSegment


def test_hashtags_are_unique_and_bounded():
    tags = _normalize_hashtags(["#TinTuc", "#tintuc", "Viet Nam", "#A", "#B", "#C", "#D", "#E", "#F", "#G"])
    assert tags[0] == "#TinTuc"
    assert len(tags) == 8
    assert len({tag.casefold() for tag in tags}) == len(tags)
    assert all(tag.startswith("#") for tag in tags)


def test_title_cleanup():
    assert _clean_title('  "Tiêu đề\nđẹp!!!"  ', "fallback") == "Tiêu đề đẹp!!!"


def test_srt_is_readable_and_sequential(tmp_path: Path):
    segments = [
        TranscriptSegment(0.0, 2.2, "Hello world"),
        TranscriptSegment(2.2, 5.5, "Second sentence with enough words to wrap onto another subtitle line."),
    ]
    segments[0].vietnamese = "Xin chào mọi người"
    segments[1].vietnamese = "Đây là câu phụ đề tiếng Việt dài để kiểm tra xuống dòng."
    target = write_srt(segments, tmp_path / "test.srt")
    text = target.read_text(encoding="utf-8")
    assert "1\n00:00:00,000 --> 00:00:02,200" in text
    assert "2\n00:00:02,200 --> 00:00:05,500" in text
    assert "Xin chào mọi người" in text
    assert target.exists()
