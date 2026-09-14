from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .config import CONFIG
from .douyin_browser import browser_download_video
from .douyin_source import _chrome_profile_available, _is_valid_video, _search_urls, _video_duration


MIN_VIDEO_SECONDS = CONFIG.min_video_seconds


def _download_with_ytdlp(url: str, target: Path) -> bool:
    command = [
        "yt-dlp", "--no-playlist", "--format", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--merge-output-format", "mp4", "--output", str(target), url,
    ]
    cookie_file = os.getenv("OPENPILOT_DOUYIN_COOKIES", "").strip()
    if cookie_file:
        command[-1:-1] = ["--cookies", str(Path(cookie_file).expanduser())]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=CONFIG.download_timeout_s)
    except FileNotFoundError:
        command[0:1] = [os.environ.get("PYTHON", "python"), "-m", "yt_dlp"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=CONFIG.download_timeout_s)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0 and target.exists() and _is_valid_video(target)


def _try_browser(url: str, target: Path) -> bool:
    print("[DOUYIN]   Browser capture (bounded session)...", flush=True)
    if not browser_download_video(url, target, CONFIG.browser_timeout_ms):
        return False
    duration = _video_duration(target) or 0.0
    if duration <= MIN_VIDEO_SECONDS:
        print(f"[DOUYIN]   Browser video too short ({duration:.1f}s <= {MIN_VIDEO_SECONDS:.0f}s) -> discard", flush=True)
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        return False
    if not _is_valid_video(target):
        print("[DOUYIN]   Browser capture is not a complete playable video -> discard", flush=True)
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        return False
    print(f"[DOUYIN]   Browser video duration: {duration:.1f}s", flush=True)
    return True


def acquire_douyin_batch(query: str, output_dir: Path, limit: int = 10) -> list[tuple[Path, str]]:
    requested = max(1, int(limit))
    output_dir.mkdir(parents=True, exist_ok=True)
    urls = _search_urls(query, limit=requested)
    print(f"[DOUYIN] Search query: {query}", flush=True)
    print(f"[DOUYIN] Candidates found: {len(urls)} | Target: {requested} | Minimum duration: >{MIN_VIDEO_SECONDS:.0f}s", flush=True)
    if not urls:
        raise RuntimeError(f"No public Douyin video URLs were discovered for '{query}'.")

    successes: list[tuple[Path, str]] = []
    errors: list[str] = []
    for candidate_number, url in enumerate(urls, 1):
        if len(successes) >= requested:
            break
        target = output_dir / f"douyin-{len(successes) + 1:02d}.mp4"
        print(f"[DOUYIN] Trying {candidate_number}/{len(urls)} | downloaded={len(successes)}/{requested}", flush=True)
        try:
            print("[DOUYIN]   Direct yt-dlp download...", flush=True)
            if _download_with_ytdlp(url, target):
                duration = _video_duration(target) or 0.0
                if duration > MIN_VIDEO_SECONDS:
                    print(f"[DOUYIN]   OK direct | duration={duration:.1f}s", flush=True)
                    successes.append((target, url))
                    continue
            try:
                target.unlink()
            except FileNotFoundError:
                pass

            if _try_browser(url, target):
                successes.append((target, url))
                continue
            errors.append("candidate inaccessible or shorter than minimum duration")
        except Exception as exc:
            errors.append(str(exc))
            print(f"[DOUYIN]   SKIP {exc}", flush=True)
            try:
                target.unlink()
            except FileNotFoundError:
                pass

    print(f"[DOUYIN] Result: {len(successes)}/{requested} downloaded", flush=True)
    if not successes:
        detail = errors[-1] if errors else "no complete playable candidate"
        raise RuntimeError(f"No accessible public Douyin video longer than {MIN_VIDEO_SECONDS:.0f}s found. {detail}")
    if len(successes) < requested:
        print(f"[DOUYIN] WARN only {len(successes)}/{requested} accessible videos were found", flush=True)
    return successes
