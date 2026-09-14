# OpenPilot Studio 🎬🤖

> **AI Content Factory — một lệnh tự động tìm trend, lấy media được phép sử dụng, dịch tiếng Việt, tạo giọng AI, dựng video, tạo tiêu đề/hashtag và xuất bản qua API chính thức.**

## 🚀 One-command AUTO

```bash
openpilot auto
```

Pipeline:

```text
Trend → permitted video → Whisper → AI Vietnamese → subtitles → AI voice → FFmpeg → title/description/hashtags → official publisher
```

## API configuration

Required:

```text
YOUTUBE_API_KEY=your_youtube_data_api_key
PEXELS_API_KEY=your_pexels_api_key
OPENPILOT_API_KEY=your_openai_compatible_api_key
```

AI options:

```text
OPENPILOT_MODEL=gpt-5-mini
OPENPILOT_TTS_MODEL=gpt-4o-mini-tts
OPENPILOT_TTS_VOICE=alloy
OPENPILOT_TREND_QUERY=trending vietnam
```

Publishing is controlled explicitly:

```text
OPENPILOT_PUBLISH=none
```

For TikTok:

```text
OPENPILOT_PUBLISH=tiktok
TIKTOK_ACCESS_TOKEN=your_authorized_user_token
TIKTOK_PRIVACY=SELF_ONLY
```

For YouTube:

```text
OPENPILOT_PUBLISH=youtube
YOUTUBE_ACCESS_TOKEN=your_oauth_access_token
YOUTUBE_PRIVACY=private
```

Use `SELF_ONLY`/`private` for the first test, then change visibility only after the official platform app and account authorization/audit requirements are satisfied.

## Install

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
pip install -e ".[dev]"
pip install -e ".[media]"
```

FFmpeg must be available in PATH.

## What AUTO does

1. Finds a trend through the official YouTube Data API.
2. Gets a permitted stock video through Pexels API.
3. Transcribes speech with Whisper.
4. Translates transcript segments into natural Vietnamese with the configured AI model.
5. Creates Vietnamese SRT subtitles.
6. Generates Vietnamese AI voice audio.
7. Renders/muxes the final 9:16 video with FFmpeg.
8. Generates title, description and hashtags with AI.
9. If `OPENPILOT_PUBLISH` is configured, uploads through an official publisher integration.
10. Writes `output/auto-result.json` with the run result.

## Official publishing

TikTok uses the Content Posting API and requires a registered app, user authorization and the `video.publish` scope for Direct Post. Unaudited clients are restricted to private viewing. YouTube uploads use the official YouTube Data API `videos.insert` endpoint and require OAuth authorization with a YouTube upload scope. OpenPilot does not bypass platform protections.

## Safety / rights

Only process media that you own or are authorized to reuse. OpenPilot does not bypass watermarks, CAPTCHA, login walls, DRM, rate limits or other platform protections. Keep publishing private during testing.
