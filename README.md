# OpenPilot Studio 🎬🤖

> **AI Content Factory — tự động tìm trend, lấy video từ nguồn được phép, xử lý thành video tiếng Việt và chuẩn bị xuất bản.**

OpenPilot Studio is an open-source, local-first content automation layer. The automation entry point is now `openpilot auto`: trend discovery → permitted media acquisition → Whisper transcription → subtitles → vertical render → publish-ready output.

## ✨ v0.4 — Automatic mode

- 🔥 Automatic trend discovery through the official YouTube Data API
- 📥 Automatic video acquisition through the permitted Pexels API
- 🎙️ Whisper transcription via `faster-whisper`
- 📝 SRT subtitle generation
- 📱 9:16 / 1080×1920 social-video rendering with FFmpeg
- 🧠 Modular AI translation/prompting architecture
- 📤 Publisher abstraction for TikTok, YouTube Shorts, Facebook Reels and Instagram Reels
- 🛡️ No bypassing of platform protections, CAPTCHAs or access controls
- ⚖️ Designed for content the user owns or is authorized to reuse

## Automatic mode

After configuring the official API credentials, one command starts the pipeline:

```bash
openpilot auto
```

Required environment variables:

```text
YOUTUBE_API_KEY=your_youtube_data_api_key
PEXELS_API_KEY=your_pexels_api_key
```

Optional trend query:

```text
OPENPILOT_TREND_QUERY=trending vietnam
```

The current automatic stage creates a processed video and subtitle file, then stops at `ready_for_publish`. Actual publishing is intentionally kept behind official platform authentication/authorization so OpenPilot cannot accidentally upload to a user's account.

## Quick start

Install the core project:

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS/Linux
source .venv/bin/activate

pip install -e ".[dev]"
```

For automatic video processing:

```bash
pip install -e ".[media]"
```

Install **FFmpeg** and make sure `ffmpeg` and `ffprobe` are available in PATH.

Manual processing is still available:

```bash
openpilot video input.mp4
```

## Architecture

```text
                    OpenPilot Studio AUTO
                           │
                           ↓
                    🔥 Trend Engine
                           │
                           ↓
                📥 Permitted Acquisition
                           │
                           ↓
              🎙️ Whisper → 🇻🇳 AI Language
                           │
                           ↓
                📝 Subtitle + 🎬 FFmpeg
                           │
                           ↓
                  🤖 AI Packaging
                           │
                           ↓
                    Approval Gateway
                           │
                           ↓
                   Official Publishers
                           │
          TikTok / YouTube / Facebook / Instagram
```

## Project structure

```text
src/openpilot/
├── agent.py
├── planner.py
├── providers.py
├── trends.py
├── auto_pipeline.py   # automatic trend + permitted acquisition + processing
├── pipeline.py        # Whisper + SRT + FFmpeg
├── publishers.py      # official publisher abstraction
└── cli.py             # openpilot auto / video / plan / github / test
```

## Rights & platform safety

OpenPilot does not attempt to defeat watermarks, CAPTCHA, login walls, rate limits, DRM or other platform protections. Automatic acquisition should use an API or source where the user has permission to download and reuse the media. Publishing should use the platform's official API and explicit account authorization.
