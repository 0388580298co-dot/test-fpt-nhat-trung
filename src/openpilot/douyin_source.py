from __future__ import annotations

import html
import re
import subprocess
from pathlib import Path
from urllib.parse import quote_plus, unquote
from urllib.request import Request, urlopen


DOUYIN_VIDEO_RE = re.compile(r"https?://(?:www\.)?douyin\.com/video/\d+[^\"'<>\s&]+|https?://v\.douyin\.com/[A-Za-z0-9_-]+/?")


def _search_urls(query: str, limit: int = 10) -> list[str]:
    """Find publicly indexed Douyin video URLs without logging in or bypassing access controls."""
    search = f"site:douyin.com/video {query}"
    url = f"https://www.bing.com/search?q={quote_plus(search)}&count={limit}"
    request = Request(url, headers={"User-Agent": "OpenPilot-Studio/0.6"})
    with urlopen(request, timeout=30) as response:
        page = response.read().decode("utf-8", errors="replace")

    found: list[str] = []
    for match in DOUYIN_VIDEO_RE.findall(html.unescape(page)):
        clean = unquote(match).rstrip(".,)")
        if clean not in found:
            found.append(clean)
        if len(found) >= limit:
            break
    return found


def _download_public_url(url: str, output_dir: Path, index: int) -> tuple[Path, str]:
    """Download a public Douyin URL through yt-dlp without cookies or authentication.

    If the site asks for cookies, CAPTCHA, login, or another access-control step,
    yt-dlp is not given a workaround; the item is simply skipped by the caller.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"douyin-{index}.mp4"
    command = [
        "yt-dlp",
        "--no-playlist",
        "--format",
        "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--merge-output-format",
        "mp4",
        "--output",
        str(target),
        url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=240)
    if result.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:]
        raise RuntimeError("Douyin download failed: " + (detail[0] if detail else "unknown error"))
    return target, url


def acquire_douyin(query: str, output_dir: Path, limit: int = 10) -> tuple[Path, str]:
    """Discover and download the first accessible public Douyin video for a topic."""
    try:
        urls = _search_urls(query, limit=limit)
    except Exception as exc:
        raise RuntimeError(f"Douyin public search failed: {exc}") from exc

    errors: list[str] = []
    for index, url in enumerate(urls, 1):
        try:
            return _download_public_url(url, output_dir, index)
        except Exception as exc:
            errors.append(str(exc))
            continue

    detail = errors[-1] if errors else "no public Douyin video URLs were indexed for this topic"
    raise RuntimeError(f"No accessible public Douyin video found for '{query}'. {detail}")
