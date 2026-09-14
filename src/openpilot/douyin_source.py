from __future__ import annotations

import html
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
    # Shorter keyword queries are much more likely to have indexed results than
    # sending a long Vietnamese trend title verbatim.
    variants = [
        query,
        " ".join(query.split()[:6]),
        "热门 视频",
    ]
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
    """Read the normal public Douyin search page when it exposes video links."""
    url = f"https://www.douyin.com/search/{quote_plus(query)}?type=general"
    try:
        return _extract_urls(_fetch(url), limit)
    except Exception:
        return []


def _search_urls(query: str, limit: int = 10) -> list[str]:
    """Find publicly exposed Douyin video URLs using ordinary public pages/search."""
    found: list[str] = []

    # Try Douyin's ordinary public search page first, then public search engines.
    for url in _search_direct_douyin(query, limit):
        if url not in found:
            found.append(url)
    for engine in ("bing", "duckduckgo"):
        for url in _search_engine_urls(query, engine, limit):
            if url not in found:
                found.append(url)
            if len(found) >= limit:
                return found
    return found[:limit]


def _download_public_url(url: str, output_dir: Path, index: int) -> tuple[Path, str]:
    """Download a public Douyin URL with yt-dlp, without cookies or authentication."""
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"douyin-{index}.mp4"
    command = [
        "yt-dlp",
        "--no-playlist",
        "--format", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--merge-output-format", "mp4",
        "--output", str(target),
        url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=240)
    if result.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:]
        raise RuntimeError("Douyin download failed: " + (detail[0] if detail else "unknown error"))
    return target, url


def acquire_douyin(query: str, output_dir: Path, limit: int = 10) -> tuple[Path, str]:
    """Discover public URLs and return the first successfully downloaded video.

    No login credentials, cookies, CAPTCHA workarounds, DRM removal, or anti-bot
    bypasses are used. Inaccessible results are skipped.
    """
    urls = _search_urls(query, limit=limit)
    if not urls:
        raise RuntimeError(f"No public Douyin video URLs were indexed for '{query}'.")

    errors: list[str] = []
    for index, url in enumerate(urls, 1):
        try:
            return _download_public_url(url, output_dir, index)
        except Exception as exc:
            errors.append(str(exc))

    detail = errors[-1] if errors else "all discovered URLs were inaccessible"
    raise RuntimeError(f"No accessible public Douyin video found for '{query}'. {detail}")
