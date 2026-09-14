from __future__ import annotations

import html
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote_plus, unquote
from urllib.request import Request, urlopen

DOUYIN_VIDEO_RE = re.compile(
    r"https?://(?:www\.)?douyin\.com/video/\d+(?:[^\"'<>\s&]|%[0-9A-Fa-f]{2})*|https?://v\.douyin\.com/[A-Za-z0-9_-]+/?"
)


def _extract_urls(page: str, limit: int) -> list[str]:
    page = unquote(html.unescape(page))
    found: list[str] = []
    for match in DOUYIN_VIDEO_RE.findall(page):
        clean = match.rstrip(".,);\"'")
        if clean not in found:
            found.append(clean)
        if len(found) >= limit:
            break
    return found


def _fetch(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _search_engine_urls(query: str, engine: str, limit: int) -> list[str]:
    variants = [query, " ".join(query.split()[:6]), "热门 视频"]
    found: list[str] = []
    for term in variants:
        if engine == "bing":
            search = f"site:douyin.com/video {term}"
            url = f"https://www.bing.com/search?q={quote_plus(search)}&count=50"
        else:
            search = f"site:douyin.com/video {term}"
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(search)}"
        try:
            for item in _extract_urls(_fetch(url), limit):
                if item not in found:
                    found.append(item)
                if len(found) >= limit:
                    return found
        except Exception:
            continue
    return found


def _search_direct_douyin(query: str, limit: int) -> list[str]:
    url = f"https://www.douyin.com/search/{quote_plus(query)}?type=general"
    try:
        return _extract_urls(_fetch(url), limit)
    except Exception:
        return []


def _search_urls(query: str, limit: int = 10) -> list[str]:
    found: list[str] = []
    for url in _search_direct_douyin(query, limit):
        if url not in found:
            found.append(url)
    for engine in ("bing", "duckduckgo"):
        for url in _search_engine_urls(query, engine, limit):
            if url not in found:
                found.append(url)
            if len(found) >= limit:
                return found[:limit]
    return found[:limit]


def _download_public_url(url: str, output_dir: Path, index: int) -> tuple[Path, str]:
    """Download with yt-dlp; optional cookies may be supplied by the account owner."""
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"douyin-{index}.mp4"
    command = [
        "yt-dlp",
        "--no-playlist",
        "--format", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--merge-output-format", "mp4",
        "--output", str(target),
    ]
    cookies = os.getenv("OPENPILOT_DOUYIN_COOKIES", "").strip()
    if cookies:
        cookie_path = Path(cookies).expanduser()
        if not cookie_path.is_file():
            raise RuntimeError(f"Douyin cookie file not found: {cookie_path}")
        command.extend(["--cookies", str(cookie_path)])
    command.append(url)

    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=240)
    if result.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        lines = (result.stderr or result.stdout).strip().splitlines()
        detail = lines[-1] if lines else "unknown error"
        raise RuntimeError("Douyin download failed: " + detail)
    return target, url


def acquire_douyin_batch(query: str, output_dir: Path, limit: int = 10) -> list[tuple[Path, str]]:
    """Find up to ``limit`` public candidates and download every accessible one.

    If OPENPILOT_DOUYIN_COOKIES points to a cookie file explicitly supplied by the
    user/account owner, yt-dlp may use it. This does not solve CAPTCHA challenges,
    bypass anti-bot controls, remove DRM, or obtain credentials automatically.
    Inaccessible candidates are skipped so one blocked video does not stop AUTO.
    """
    urls = _search_urls(query, limit=limit)
    if not urls:
        raise RuntimeError(f"No public Douyin video URLs were indexed for '{query}'.")

    successes: list[tuple[Path, str]] = []
    errors: list[str] = []
    print(f"[3/8] Tìm thấy {len(urls)} video Douyin để thử tải", flush=True)
    for index, url in enumerate(urls, 1):
        print(f"[4/8] Đang thử tải video {index}/{len(urls)}...", flush=True)
        try:
            item = _download_public_url(url, output_dir, index)
            successes.append(item)
            print(f"       OK video {index}/{len(urls)}", flush=True)
        except Exception as exc:
            errors.append(str(exc))
            print(f"       Bỏ qua video {index}/{len(urls)}: {exc}", flush=True)
    if not successes:
        detail = errors[-1] if errors else "all discovered URLs were inaccessible"
        raise RuntimeError(f"No accessible public Douyin video found for '{query}'. {detail}")
    return successes


def acquire_douyin(query: str, output_dir: Path, limit: int = 10) -> tuple[Path, str]:
    """Compatibility wrapper: return the first successfully downloaded candidate."""
    return acquire_douyin_batch(query, output_dir, limit=limit)[0]
