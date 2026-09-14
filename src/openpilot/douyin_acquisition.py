from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .config import CONFIG
from .douyin_browser import browser_download_video
from .douyin_source import _is_valid_video, _search_urls, _video_duration

MIN_VIDEO_SECONDS = CONFIG.min_video_seconds


def _download_with_ytdlp(url: str, target: Path) -> bool:
    command = ["yt-dlp", "--no-playlist", "--format", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b", "--merge-output-format", "mp4", "--output", str(target)]
    cookie_file = os.getenv("OPENPILOT_DOUYIN_COOKIES", "").strip()
    if cookie_file:
        cookie_path = Path(cookie_file).expanduser()
        if not cookie_path.is_file():
            return False
        command.extend(["--cookies", str(cookie_path)])
    command.append(url)
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=CONFIG.download_timeout_s)
    except FileNotFoundError:
        command[0:1] = [os.environ.get("PYTHON", "python"), "-m", "yt_dlp"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=CONFIG.download_timeout_s)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    except subprocess.TimeoutExpired:
        print("[DOUYIN]   yt-dlp timeout -> next candidate", flush=True)
        return False
    if result.returncode != 0 or not target.exists() or not _is_valid_video(target):
        if target.exists():
            duration = _video_duration(target) or 0.0
            if duration <= MIN_VIDEO_SECONDS:
                print(f"[DOUYIN]   Direct video too short ({duration:.1f}s <= {MIN_VIDEO_SECONDS:.0f}s) -> discard", flush=True)
            else:
                print("[DOUYIN]   Direct file failed media validation -> discard", flush=True)
            target.unlink(missing_ok=True)
        return False
    return True


def acquire_douyin_batch(query: str, output_dir: Path, limit: int = 10) -> list[tuple[Path, str]]:
    requested = max(1, int(limit))
    output_dir.mkdir(parents=True, exist_ok=True)
    all_urls = _search_urls(query, limit=requested)
    max_candidates = min(len(all_urls), max(requested * 3, 12))
    urls = all_urls[:max_candidates]
    print(f"[DOUYIN] Search query: {query}", flush=True)
    print(f"[DOUYIN] Candidates found: {len(urls)} | Target: {requested} | Minimum duration: >{MIN_VIDEO_SECONDS:.0f}s", flush=True)
    if not urls:
        raise RuntimeError(f"No public Douyin video URLs were discovered for '{query}'.")

    successes: list[tuple[Path, str]] = []
    for candidate_number, url in enumerate(urls, 1):
        if len(successes) >= requested:
            break
        target = output_dir / f"douyin-{len(successes) + 1:02d}.mp4"
        print(f"[DOUYIN] Trying {candidate_number}/{len(urls)} | downloaded={len(successes)}/{requested}", flush=True)
        try:
            print("[DOUYIN]   Direct yt-dlp download...", flush=True)
            if _download_with_ytdlp(url, target):
                duration = _video_duration(target) or 0.0
                print(f"[DOUYIN]   OK direct | duration={duration:.1f}s", flush=True)
                successes.append((target, url))
                continue
            print("[DOUYIN]   Browser capture (bounded session)...", flush=True)
            if browser_download_video(url, target, CONFIG.browser_timeout_ms):
                duration = _video_duration(target) or 0.0
                if duration > MIN_VIDEO_SECONDS and _is_valid_video(target):
                    print(f"[DOUYIN]   OK browser | duration={duration:.1f}s", flush=True)
                    successes.append((target, url))
                    continue
                print(f"[DOUYIN]   Browser result rejected | duration={duration:.1f}s", flush=True)
            target.unlink(missing_ok=True)
        except Exception as exc:
            target.unlink(missing_ok=True)
            print(f"[DOUYIN]   SKIP {exc}", flush=True)

    print(f"[DOUYIN] Result: {len(successes)}/{requested} downloaded", flush=True)
    if not successes:
        raise RuntimeError(f"No accessible public Douyin video longer than {MIN_VIDEO_SECONDS:.0f}s found for '{query}'.")
    if len(successes) < requested:
        print(f"[DOUYIN] WARN only {len(successes)}/{requested} accessible videos were found", flush=True)
    return successes
