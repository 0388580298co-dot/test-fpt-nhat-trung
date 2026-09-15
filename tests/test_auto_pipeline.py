from pathlib import Path

from openpilot.auto_pipeline import _segments_from_script
from openpilot.douyin_acquisition import _is_valid_video
from openpilot.transcription import TranscriptSegment


def test_narration_segments_cover_full_video():
    segments = _segments_from_script(
        "Đây là câu đầu tiên. Đây là câu thứ hai để kiểm tra phụ đề.",
        20.0,
    )
    assert segments
    assert segments[0].start == 0.0
    assert abs(segments[-1].end - 20.0) < 0.001
    assert all(segment.end > segment.start for segment in segments)
    assert all(segment.vietnamese for segment in segments)


def test_narration_subtitles_stay_compact():
    segments = _segments_from_script(
        "Một câu thuyết minh rất dài để kiểm tra việc chia nội dung thành các đoạn phụ đề ngắn và dễ đọc trên màn hình điện thoại.",
        15.0,
    )
    assert segments
    assert all(len(segment.vietnamese.split()) <= 12 for segment in segments)


def test_transcript_segment_can_hold_vietnamese():
    segment = TranscriptSegment(0.0, 2.0, "Hello")
    segment.vietnamese = "Xin chào"
    assert segment.vietnamese == "Xin chào"


def test_douyin_validator_rejects_missing_file(tmp_path: Path):
    assert _is_valid_video(tmp_path / "missing.mp4") is False
