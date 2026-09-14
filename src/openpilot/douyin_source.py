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


def _search_engine_urls(query: str, engine: str, limit: int) -> list[str]:
    search = f'site:douyin.com/video "{query}"'
    if engine == "bing":
        url = f"https://www.bing.com/search?q={quote_plus(search)}&count={min(limit, 50)}"
    else:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(search)}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OpenPilot-Studio/0.6"})
    with urlopen(request, timeout=30) as response:
        page = response.read().decode("utf-8", errors="replace")

    found: list[str] = []
    page = html.unescape(page)
    # Search engines may HTML-escape query URLs or put them behind redirects.
    candidates = DOUYIN_VIDEO_RE.findall(page)
    if not candidates:
        candidates = DOUYIN_VIDEO_RE.findall(unquote(page))
    for match in candidates:
        clean = unquote(match).rstrip(".,);\"'")
        if clean not in found:
            found.append(clean)
        if len(found) >= limit:
            break
    return found


def _search_urls(query: str, limit: int = 10) -> list[str]:
    """Find publicly indexed Douyin video URLs using ordinary public search."""
    found: list[str] = []
    errors: list[str] = []
    for engine in ("bing", "duckduckgo"):
        try:
            for url in _search_engine_urls(query, engine, limit):
                if url not in found:
                    found.append(url)
                if len(found) >= limit:
                    return found
        except Exception as exc:
            errors.append(f"{engine}: {exc}")
    if not found and errors:
        raise RuntimeError("; ".join(errors))
    return found


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
    """Discover several public URLs, then return the first successfully downloaded video.

    This intentionally does not use login credentials, cookies, CAPTCHA workarounds,
    DRM removal, or anti-bot bypasses. Inaccessible public results are skipped.
    """
    try:
        urls = _search_urls(query, limit=limit)
    except Exception as exc:
        raise RuntimeError(f"Douyin public search failed: {exc}") from exc

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
