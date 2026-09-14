from __future__ import annotations

import html
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote_plus, unquote
from urllib.request import Request, urlopen

DOUYIN_VIDEO_RE = re.compile(
    r"https?://(?:www\.)?douyin\.com/(?:video|shipin)/\d+(?:[^\"'<>\s&]|%[0-9A-Fa-f]{2})*"
    r"|https?://v\.douyin\.com/[A-Za-z0-9_-]+/?"
)
DOUYIN_RELATIVE_VIDEO_RE = re.compile(
    r"(?:href=[\"']?|url\()\s*(?:https?:)?//(?:www\.)?douyin\.com/(?:video|shipin)/(\d{8,30})"
    r"|/(?:video|shipin)/(\d{8,30})"
)
DOUYIN_ID_RE = re.compile(
    r"(?:aweme_id|awemeId|itemId|item_id|video_id)[\"'=: ]+([0-9]{8,30})"
)
DOUYIN_PATH_RE = re.compile(r"(?:https?:)?//(?:www\.)?douyin\.com/(?:video|shipin)/(\d{8,30})")


def _extract_urls(page: str, limit: int) -> list[str]:
    """Extract public Douyin video URLs from HTML, JSON, or relative links."""
    page = page.replace(r"\/", "/").replace(r"\u002F", "/").replace(r"\u002f", "/")
    page = unquote(html.unescape(page))
    found: list[str] = []

    def add(url: str) -> bool:
        url = url.strip().rstrip(".,);\"'")
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = "https://www.douyin.com" + url
        if not re.search(r"douyin\.com/(?:video|shipin)/\d+", url):
            return False
        if url not in found:
            found.append(url)
        return len(found) >= limit

    # Absolute Douyin URLs, including both /video/ and /shipin/ pages.
    for match in DOUYIN_VIDEO_RE.findall(page):
        if add(match):
            return found

    # Relative links such as href="/shipin/7645095798279063594".
    for match in DOUYIN_RELATIVE_VIDEO_RE.findall(page):
        video_id = match[0] or match[1]
        if add(f"https://www.douyin.com/shipin/{video_id}"):
            return found

    # Escaped/embedded Douyin paths that are not inside a normal href.
    for match in DOUYIN_PATH_RE.findall(page):
        if add(f"https://www.douyin.com/{'video' if '/video/' in match else 'shipin'}/{match}"):
            return found

    # Embedded item IDs from page JSON/state.
    for video_id in DOUYIN_ID_RE.findall(page):
        if add(f"https://www.douyin.com/video/{video_id}"):
            return found
    return found


def _fetch(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _query_variants(query: str) -> list[str]:
    clean = re.sub(r"\s+", " ", query).strip()
    clean = re.sub(r"\s*[-–—|]\s*(Đài Phát thanh.*|VTV.*|Báo.*)$", "", clean, flags=re.I)
    words = clean.split()
    variants = [
        clean,
        " ".join(words[:10]),
        "抖音 热门",
        "热门 视频",
        "热点 视频",
    ]
    return list(dict.fromkeys(v for v in variants if v))


def _search_engine_urls(query: str, engine: str, limit: int) -> list[str]:
    found: list[str] = []
    for term in _query_variants(query):
        search = f"site:douyin.com (inurl:video OR inurl:shipin) {term}"
        if engine == "bing":
            url = f"https://www.bing.com/search?q={quote_plus(search)}&count=50"
        else:
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
    found: list[str] = []
    for term in _query_variants(query):
        urls = (
            f"https://www.douyin.com/search/{quote_plus(term)}?type=video",
            f"https://www.douyin.com/search/?keyword={quote_plus(term)}&type=video",
        )
        for url in urls:
            try:
                for item in _extract_urls(_fetch(url), limit):
                    if item not in found:
                        found.append(item)
                    if len(found) >= limit:
                        return found
            except Exception:
                continue
    return found


def _search_douyin_public_pages(limit: int) -> list[str]:
    """Fallback discovery using public Douyin pages, still Douyin-only."""
    pages = (
        "https://www.douyin.com/shipin/",
        "https://www.douyin.com/search/?type=video",
        "https://www.douyin.com/htmlmap/hotchallenge_0_1",
    )
    found: list[str] = []
    for page_url in pages:
        try:
            for item in _extract_urls(_fetch(page_url), limit):
                if item not in found:
                    found.append(item)
                if len(found) >= limit:
                    return found
        except Exception:
            continue
    return found


def _search_urls(query: str, limit: int = 10) -> list[str]:
    candidate_limit = max(limit * 5, 30)
    found: list[str] = []

    # 1) Query-specific Douyin search.
    for url in _search_direct_douyin(query, candidate_limit):
        if url not in found:
            found.append(url)

    # 2) Public search engines indexing Douyin video pages.
    for engine in ("bing", "duckduckgo"):
        for url in _search_engine_urls(query, engine, candidate_limit):
            if url not in found:
                found.append(url)
            if len(found) >= candidate_limit:
                return found[:candidate_limit]

    # 3) Last-resort discovery from Douyin's own public hot/video pages.
    if len(found) < limit:
        for url in _search_douyin_public_pages(candidate_limit):
            if url not in found:
                found.append(url)
            if len(found) >= candidate_limit:
                break
    return found[:candidate_limit]


def _download_public_url(url: str, output_dir: Path, index: int) -> tuple[Path, str]:
    """Download a public Douyin URL with yt-dlp."""
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"douyin-{index:02d}.mp4"

    candidates = [url]
    shipin_match = re.search(r"douyin\.com/shipin/(\d{8,30})", url)
    if shipin_match:
        # Some yt-dlp versions recognize the canonical /video/ form more reliably.
        candidates.append(f"https://www.douyin.com/video/{shipin_match.group(1)}")

    last_error = "unknown error"
    for candidate in candidates:
        command = [
            "yt-dlp", "--no-playlist",
            "--format", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
            "--merge-output-format", "mp4", "--output", str(target),
        ]
        cookies = os.getenv("OPENPILOT_DOUYIN_COOKIES", "").strip()
        if cookies:
            cookie_path = Path(cookies).expanduser()
            if not cookie_path.is_file():
                raise RuntimeError(f"Douyin cookie file not found: {cookie_path}")
            command.extend(["--cookies", str(cookie_path)])
        command.append(candidate)

        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=240)
        if result.returncode == 0 and target.exists() and target.stat().st_size > 0:
            return target, candidate

        lines = (result.stderr or result.stdout).strip().splitlines()
        last_error = lines[-1] if lines else "unknown error"

    raise RuntimeError("Douyin download failed: " + last_error)


def acquire_douyin_batch(query: str, output_dir: Path, limit: int = 10) -> list[tuple[Path, str]]:
    """Find and download up to ``limit`` accessible public Douyin videos."""
    requested = max(1, int(limit))
    urls = _search_urls(query, limit=requested)
    if not urls:
        raise RuntimeError(
            f"No public Douyin video URLs were discovered for '{query}'. "
            "Douyin/search pages returned no video links; retry or provide your own cookies."
        )

    successes: list[tuple[Path, str]] = []
    errors: list[str] = []
    print(f"[DOUYIN] Candidates: {len(urls)} | Target: {requested}", flush=True)
    for index, url in enumerate(urls, 1):
        if len(successes) >= requested:
            break
        print(f"[DOUYIN] Trying {index}/{len(urls)} | downloaded={len(successes)}/{requested}", flush=True)
        try:
            item = _download_public_url(url, output_dir, len(successes) + 1)
            successes.append(item)
            print(f"[DOUYIN]   OK  {item[0].name}", flush=True)
        except Exception as exc:
            errors.append(str(exc))
            print(f"[DOUYIN]   SKIP {exc}", flush=True)

    if not successes:
        detail = errors[-1] if errors else "all discovered URLs were inaccessible"
        raise RuntimeError(f"No accessible public Douyin video found for '{query}'. {detail}")
    return successes


def acquire_douyin(query: str, output_dir: Path, limit: int = 10) -> tuple[Path, str]:
    """Compatibility wrapper: return the first successfully downloaded Douyin video."""
    return acquire_douyin_batch(query, output_dir, limit=limit)[0]
