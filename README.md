# OpenPilot Studio 🎬🤖

> **AI Content Factory — một lệnh tự động tìm trend, tìm và tải video Douyin, nhận diện lời thoại, dịch tiếng Việt, tạo giọng, dựng 9:16, tạo metadata và tùy chọn xuất bản qua API chính thức.**

## 🚀 One-command AUTO

```bash
openpilot auto
```

Mặc định AUTO tạo một batch **10 video Douyin**:

```text
Trend discovery
      ↓
Douyin search
      ↓
Tìm nhiều ứng viên → thử tải → lấy tối đa 10 video Douyin
      ↓
Whisper → AI Vietnamese → SRT → TTS → FFmpeg 9:16
      ↓
Title + description + unique hashtags
      ↓
10 sản phẩm hoàn chỉnh + auto-manifest.json
      ↓
Tùy chọn: TikTok / YouTube API chính thức
```

**AUTO chỉ nhận video từ Douyin. Không có Pexels/Wikimedia fallback.** Nếu Douyin không đủ video truy cập được, hệ thống báo rõ số lượng thực tế thay vì lấy nguồn khác.

## 🖥️ Professional terminal UI

Khi chạy `openpilot auto`, CLI hiển thị:

- Header OpenPilot Studio + cấu hình batch/AI/TTS/publish.
- Từng phase của pipeline.
- Số ứng viên Douyin và tiến độ tải.
- Khung riêng cho từng `VIDEO 01/10`, `VIDEO 02/10`...
- 5 stage của từng video: Whisper/AI, SRT, TTS, FFmpeg, publishing.
- Thời gian thực hiện từng stage và tổng thời gian.
- Đường dẫn video thành phẩm, title và hashtag.
- Tổng kết `Completed / Failed / Elapsed / Manifest`.

Không cần cài thêm thư viện UI.

## 🧠 AI chạy local

Để không phụ thuộc API trả phí, mặc định dùng Ollama:

```cmd
set OPENPILOT_AI_PROVIDER=local
set OPENPILOT_LOCAL_MODEL=qwen2.5:3b
set OPENPILOT_TTS_PROVIDER=pyttsx3
```

Có thể dùng model local khác bằng `OPENPILOT_LOCAL_MODEL`.

## 📦 Batch

Mặc định:

```text
OPENPILOT_BATCH_SIZE=10
```

Muốn thử nhanh 1 video:

```cmd
set OPENPILOT_BATCH_SIZE=1
openpilot auto
```

Muốn quay lại 10 video:

```cmd
set OPENPILOT_BATCH_SIZE=10
openpilot auto
```

AUTO không dừng cả batch chỉ vì một video lỗi. Video lỗi được ghi vào manifest.

## 🎯 Output

```text
output/
├── source/
│   └── douyin/              # CHỈ video tải từ Douyin
├── video-01-douyin-01.vi.srt
├── video-01-douyin-01.vi.mp3
├── video-01-douyin-01.vertical.mp4
├── video-01-douyin-01.final.mp4
├── ...
├── video-10-douyin-10.final.mp4
└── auto-manifest.json
```

`auto-manifest.json` chứa trend, chính sách nguồn `douyin_only`, số lượng yêu cầu/thực tế, đường dẫn input/output, title, hashtag, trạng thái publish và lỗi từng video.

## 🌐 Nguồn video — Douyin only

Douyin được tìm qua trang công khai và công cụ tìm kiếm, sau đó tải bằng `yt-dlp`. Có thể cung cấp cookie của chính tài khoản người dùng bằng:

```cmd
set OPENPILOT_DOUYIN_COOKIES=C:\path\cookies.txt
```

OpenPilot không vượt CAPTCHA, DRM, anti-bot, login wall hoặc cơ chế bảo vệ truy cập.

## 🔑 API configuration

Trend có thể dùng YouTube Data API:

```text
YOUTUBE_API_KEY=your_youtube_data_api_key
```

Nếu dùng AI cloud thay cho local:

```text
OPENPILOT_AI_PROVIDER=openai
OPENPILOT_API_KEY=your_api_key
OPENPILOT_MODEL=gpt-5-mini
OPENPILOT_TTS_MODEL=gpt-4o-mini-tts
OPENPILOT_TTS_VOICE=alloy
```

Trend mặc định:

```text
OPENPILOT_TREND_QUERY=trending vietnam
```

## 📤 Official publishing

Không publish mặc định:

```text
OPENPILOT_PUBLISH=none
```

TikTok:

```text
OPENPILOT_PUBLISH=tiktok
TIKTOK_ACCESS_TOKEN=your_authorized_user_token
TIKTOK_PRIVACY=SELF_ONLY
```

YouTube:

```text
OPENPILOT_PUBLISH=youtube
YOUTUBE_ACCESS_TOKEN=your_oauth_access_token
YOUTUBE_PRIVACY=private
```

Chỉ dùng token của chính tài khoản đã cấp quyền. Khi test lần đầu nên giữ `SELF_ONLY`/`private`.

## 🛠️ Install — Windows

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pip install -e ".[media]"
python -m pip install -U yt-dlp
```

FFmpeg phải có trong PATH.

## ✅ AUTO hiện có

1. Tìm trend tự động.
2. Tìm nhiều ứng viên Douyin.
3. Chỉ tải video Douyin.
4. Xử lý batch tối đa 50 video, mặc định 10.
5. Whisper speech-to-text.
6. Dịch từng đoạn sang tiếng Việt.
7. Tạo SRT tiếng Việt.
8. TTS tiếng Việt local hoặc cloud.
9. Render 9:16 bằng FFmpeg.
10. Tạo title/description/hashtags bằng AI.
11. Chuẩn hóa hashtag, loại trùng lặp.
12. Một video lỗi không làm mất cả batch.
13. Ghi `auto-manifest.json`.
14. Giao diện CLI chi tiết theo từng phase/video.
15. TikTok/YouTube publish qua API chính thức khi được cấu hình.

## ⚠️ Quyền sử dụng nội dung

Chỉ xuất bản nội dung mà bạn có quyền sử dụng. OpenPilot không vượt CAPTCHA, DRM, anti-bot, login wall, rate limit hoặc cơ chế bảo vệ của nền tảng và không tự lấy thông tin đăng nhập.
