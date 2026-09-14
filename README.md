# OpenPilot Studio 🎬🤖

> **AI Content Factory — biến video bạn có quyền sử dụng thành nội dung tiếng Việt sẵn sàng cho mạng xã hội.**

OpenPilot Studio is an open-source, local-first content automation layer built on top of the OpenPilot agent. The project is designed around a safe pipeline:

**source → speech-to-text → translation → subtitles → vertical render → approval → publishing**

## ✨ v0.3 — Content Factory foundation

- 🎙️ Optional Whisper transcription via `faster-whisper`
- 🇻🇳 Translation abstraction ready for LLM providers
- 📝 SRT subtitle generation
- 📱 9:16 / 1080×1920 social-video rendering with FFmpeg
- 🔥 Trend-source abstraction for TikTok/Douyin and other sources
- 📤 Publisher abstraction for TikTok, YouTube Shorts, Facebook Reels and Instagram Reels
- 🛡️ Dry-run publishing by default
- ⚖️ Rights-confirmation workflow: only process content you own or are authorized to reuse
- 🧩 Modular architecture for future AI voice, scoring and official API integrations

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

For video transcription:

```bash
pip install -e ".[media]"
```

Install **FFmpeg** and make sure `ffmpeg` and `ffprobe` are available in PATH.

Process a video you are authorized to use:

```python
from openpilot.pipeline import process_video

result = process_video("input.mp4", "output")
print(result.output_video)
print(result.subtitle_file)
```

## Architecture

```text
                    OpenPilot Studio
                           │
       ┌───────────────────┼───────────────────┐
       ↓                   ↓                   ↓
   Trend Engine       AI Language         Video Engine
       │                   │                   │
   TikTok/Douyin       STT + LLM            FFmpeg
   adapters            Translation          Subtitle
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ↓
                    Approval Gateway
                           ↓
                    Publishing Engine
                           ↓
        TikTok / YouTube / Facebook / Instagram
```

## Project structure

```text
src/openpilot/
├── agent.py          # coding-agent orchestration
├── planner.py        # deterministic planning
├── providers.py      # OpenAI-compatible LLM provider
├── trends.py         # trend-source abstraction
├── transcription.py  # optional Whisper STT
├── translation.py    # translation interface
├── subtitles.py      # SRT generation
├── media.py          # FFmpeg media utilities
├── pipeline.py       # video processing pipeline
├── publishers.py     # safe publishing abstraction
├── github_tool.py    # read-only GitHub inspection
├── test_runner.py    # safe pytest runner
└── cli.py            # command-line interface
```

## Important safety & platform policy

OpenPilot Studio does **not** bypass platform protections, private content, login walls, DRM, or anti-bot systems. Trend discovery is implemented as an adapter so official APIs, licensed feeds, or user-provided sources can be connected later.

Publishing is **dry-run by default**. Production integrations should use official platform APIs and explicit user authorization. The project is intended for content the user owns or has permission to reuse; automation does not grant copyright permission.

## Roadmap

- [x] v0.3 media pipeline foundation
- [x] Whisper transcription adapter
- [x] SRT subtitle generation
- [x] 9:16 social render
- [x] trend/publisher interfaces
- [ ] LLM Vietnamese translation adapter
- [ ] AI Vietnamese voice/TTS adapter
- [ ] automatic subtitle burn-in
- [ ] trend scoring (views, velocity, engagement)
- [ ] official TikTok publishing adapter
- [ ] YouTube Shorts publishing adapter
- [ ] Meta Reels publishing adapter
- [ ] web dashboard
- [ ] job queue + scheduler
- [ ] Docker sandbox
- [ ] analytics and A/B testing

## License

MIT License.
