# OpenPilot Studio — AI Content Factory

OpenPilot Studio is a Windows-friendly content automation pipeline designed around a clear workflow:

**Douyin → validate (>10s) → clean audio → Whisper → Vietnamese translation → SRT → Vietnamese TTS → 9:16 H.264/AAC MP4 → optional official publishing**

## 0.7.0 highlights

- Douyin is the only automatic video source.
- Videos must be **strictly longer than 10 seconds**.
- Invalid, partial, tiny, HTML, JSON and playlist responses are rejected.
- Douyin browser acquisition is bounded; a failed candidate moves to the next candidate instead of hanging indefinitely.
- Browser capture prefers the exact media response received by the rendered page.
- Whisper receives a normalized mono 16 kHz speech track with denoise, dynamic normalization and VAD.
- Repeated/no-speech hallucinations are filtered.
- Translation is performed in small batches so compact local models do not overflow their context window.
- Vietnamese subtitles are readable and burned into the final 9:16 video.
- Final video is validated as H.264 + AAC + yuv420p at 1080×1920.
- Every output is atomic: incomplete render files are never promoted to the final filename.
- `openpilot doctor` checks the local environment before a run.
- `output/auto-manifest.json` records each source, result, duration and failure.

## Windows setup

```cmd
cd C:\Users\03885\test-fpt-nhat-trung
.venv\Scripts\activate
pip install -e ".[all]"
python -m playwright install chromium
```

FFmpeg and ffprobe must be available in `PATH`.

For local AI, start Ollama and make the selected model available. The default model is `qwen2.5:3b`.

## Diagnostics

Run this first:

```cmd
openpilot doctor
```

It checks FFmpeg, ffprobe, yt-dlp, faster-whisper, pyttsx3, Playwright and Ollama.

## Automatic factory

Recommended first run:

```cmd
set OPENPILOT_BATCH_SIZE=1
set OPENPILOT_AI_PROVIDER=local
set OPENPILOT_LOCAL_MODEL=qwen2.5:3b
set OPENPILOT_TTS_PROVIDER=pyttsx3
openpilot auto
```

After one clean result:

```cmd
set OPENPILOT_BATCH_SIZE=10
openpilot auto
```

Useful controls:

```cmd
set OPENPILOT_MIN_VIDEO_SECONDS=10
set OPENPILOT_BROWSER_TIMEOUT_MS=20000
set OPENPILOT_DOWNLOAD_TIMEOUT=45
set OPENPILOT_MAX_BROWSER_MEDIA=5
```

## Output

```text
output/
  auto-manifest.json
  source/
    douyin/
      douyin-01.mp4
  video-01-douyin-01.vi.srt
  video-01-douyin-01.vi.mp3
  video-01-douyin-01.final.mp4
```

The `.final.mp4` is the deliverable: 1080×1920, H.264 video, AAC audio, Vietnamese subtitles burned into the image.

## Commands

```text
openpilot doctor       Check local dependencies
openpilot auto         Run the Douyin AI content factory
openpilot video FILE   Process one local video
openpilot test         Run regression tests
openpilot plan TASK    Generate a task plan
openpilot github REPO  Inspect a public GitHub repository
```

## Publishing

Publishing is disabled by default. When enabled, the project uses official platform APIs and requires the corresponding account/app authorization.

Supported modes currently exposed by AUTO:

```cmd
set OPENPILOT_PUBLISH=none
set OPENPILOT_PUBLISH=tiktok
set OPENPILOT_PUBLISH=youtube
```

Use a private/self-only destination while testing publishing credentials.

## Acquisition boundaries

The acquisition layer uses normal public Douyin pages, optional user-provided cookies, yt-dlp and a rendered browser session. It does **not** implement CAPTCHA solving, DRM circumvention, login bypass, watermark/protection bypass or anti-bot/access-control bypass.

## Project structure

```text
src/openpilot/
  auto_pipeline.py       orchestration and reporting
  douyin_acquisition.py  bounded Douyin acquisition
  douyin_browser.py      browser media capture
  douyin_source.py       Douyin discovery and validation helpers
  transcription.py       audio cleanup + Whisper
  ai_content.py          translation, metadata and TTS
  subtitles.py           SRT generation
  media.py               final 9:16 render + validation
  official_publishers.py official publishing adapters
  doctor.py              environment diagnostics
  config.py              centralized runtime settings
```
