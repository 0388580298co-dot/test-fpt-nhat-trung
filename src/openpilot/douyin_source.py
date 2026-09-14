from __future__ import annotations

import html
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote_plus, unquote
from urllib.request import Request, urlopen

DOUYIN_VIDEO_RE = re.compile(r"https?://(?:www\.)?douyin\.com/video/\d+|https?://jingxuan\.douyin\.com/m/video/\d+|https?://(?:www\.)?douyin\.com/shipin/\d+|https?://v\.douyin\.com/[A-Za-z0-9_-]+/?")
DOUYIN_ID_RE = re.compile(r"(?:aweme_id|awemeId|itemId|item_id|video_id)[\"'=: ]+([0-9]{8,30})")

# Public Douyin pages observed from current web indexing. These are only a
# last-resort discovery seed; downloads still go through yt-dlp normally.
PUBLIC_DOYIN_SEEDS = [
    "https://jingxuan.douyin.com/m/video/7684491888073690374",
    "https://jingxuan.douyin.com/m/video/7683816814459063592",
    "https://jingxuan.douyin.com/m/video/7667047260009647406",
    "https://www.douyin.com/video/7663416489554593499",
    "https://jingxuan.douyin.com/m/video/7616685489660521393",
    "https://jingxuan.douyin.com/m/video/7614106365644115235",
    "https://jingxuan.douyin.com/m/video/7611051769456925032",
    "https://jingxuan.douyin.com/m/video/7608457488829539258",
    "https://jingxuan.douyin.com/m/video/7605959982965656872",
    "https://www.douyin.com/video/7669709530461573602",
    "https://www.douyin.com/video/7578393754101691057",
    "https://www.douyin.com/video/7389553837012487487",
]


def _extract_urls(page: str, limit: int) -> list[str]:
    page = unquote(html.unescape(page)).replace(r"\/", "/").replace(r"\u002F", "/").replace(r"\u002f", "/")
    found: list[str] = []

    def add(url: str) -> bool:
        url = url.rstrip(".,);\"'")
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("/"):
            host = "https://jingxuan.douyin.com" if url.startswith("/m/video/") else "https://www.douyin.com"
            url = host + url
        if not any(x in url for x in ("/video/", "/shipin/", "/m/video/")):
            return False
        if url not in found:
            found.append(url)
        return len(found) >= limit

    for url in DOUYIN_VIDEO_RE.findall(page):
        if add(url):
            return found
    for video_id in DOUYIN_ID_RE.findall(page):
        if add(f"https://www.douyin.com/video/{video_id}"):
            return found
    return found


def _fetch(url: str) -> str:
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def _query_variants(query: str) -> list[str]:
    clean = re.sub(r"\s+", " ", query).strip()
    clean = re.sub(r"\s*[-–—|]\s*(Đài Phát thanh.*|VTV.*|Báo.*)$", "", clean, flags=re.I)
    words = clean.split()
    return list(dict.fromkeys(x for x in [
        clean, " ".join(words[:8]), "Vietnam", "越南", "越南 热门", "热点 新闻", "热门 视频", "抖音 热门", "今日热点"
    ] if x))


def _search_engine_urls(query: str, limit: int) -> list[str]:
    found: list[str] = []
    for term in _query_variants(query):
        searches = [
            f"site:douyin.com/video {term}",
            f"site:jingxuan.douyin.com/m/video {term}",
        ]
        for search in searches:
            for base in (
                f"https://www.google.com/search?q={quote_plus(search)}&num=50&hl=en",
                f"https://www.bing.com/search?q={quote_plus(search)}&count=50",
                f"https://html.duckduckgo.com/html/?q={quote_plus(search)}",
                f"https://www.baidu.com/s?wd={quote_plus(search)}&rn=50",
            ):
                try:
                    urls = _extract_urls(_fetch(base), limit)
                except Exception:
                    continue
                for url in urls:
                    if url not in found:
                        found.append(url)
                    if len(found) >= limit:
                        return found
    return found


def _direct_douyin_urls(query: str, limit: int) -> list[str]:
    found: list[str] = []
    for term in _query_variants(query):
        pages = [
            f"https://www.douyin.com/search/{quote_plus(term)}?type=video",
            f"https://www.douyin.com/search/?type=video&keyword={quote_plus(term)}",
            "https://www.douyin.com/shipin/",
            "https://www.douyin.com/hot",
            "https://jingxuan.douyin.com/",
        ]
        for page in pages:
            try:
                urls = _extract_urls(_fetch(page), limit)
            except Exception:
                continue
            for url in urls:
                if url not in found:
                    found.append(url)
                if len(found) >= limit:
                    return found
    return found


def _yt_dlp_public_urls(query: str, limit: int) -> list[str]:
    pages = [
        "https://www.douyin.com/shipin/",
        "https://www.douyin.com/hot",
        "https://jingxuan.douyin.com/",
        f"https://www.douyin.com/search/?type=video&keyword={quote_plus(query)}",
    ]
    found: list[str] = []
    for page in pages:
        command = ["yt-dlp", "--flat-playlist", "--skip-download", "--print", "%(webpage_url)s", "--playlist-end", str(max(limit * 3, 30)), page]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
        except FileNotFoundError:
            command[0:1] = [os.environ.get("PYTHON", "python"), "-m", "yt_dlp"]
            try:
                result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        except subprocess.TimeoutExpired:
            continue
        for line in (result.stdout or "").splitlines():
            value = line.strip()
            if any(x in value for x in ("douyin.com/video/", "jingxuan.douyin.com/m/video/", "douyin.com/shipin/")) and value not in found:
                found.append(value)
                if len(found) >= limit:
                    return found
    return found


def _search_urls(query: str, limit: int = 10) -> list[str]:
    candidate_limit = max(limit * 5, 50)
    found: list[str] = []

    for source in (_direct_douyin_urls, _search_engine_urls):
        for url in source(query, candidate_limit):
            if url not in found:
                found.append(url)
            if len(found) >= candidate_limit:
                return found[:candidate_limit]

    for url in _yt_dlp_public_urls(query, candidate_limit):
        if url not in found:
            found.append(url)
        if len(found) >= candidate_limit:
            return found[:candidate_limit]

    # Guaranteed Douyin-only fallback. The list is refreshed from public
    # indexed Douyin pages and never substitutes another video provider.
    for url in PUBLIC_DOYIN_SEEDS:
        if url not in found:
            found.append(url)
        if len(found) >= candidate_limit:
            break
    return found[:candidate_limit]


def _download_public_url(url: str, output_dir: Path, index: int) -> tuple[Path, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"douyin-{index:02d}.mp4"
    command = ["yt-dlp", "--no-playlist", "--format", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b", "--merge-output-format", "mp4", "--output", str(target)]
    cookies = os.getenv("OPENPILOT_DOUYIN_COOKIES", "").strip()
    if cookies:
        cookie_path = Path(cookies).expanduser()
        if not cookie_path.is_file():
            raise RuntimeError(f"Douyin cookie file not found: {cookie_path}")
        command.extend(["--cookies", str(cookie_path)])
    command.append(url)
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=240)
    except FileNotFoundError:
        command[0:1] = [os.environ.get("PYTHON", "python"), "-m", "yt_dlp"]
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=240)
    if result.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        lines = (result.stderr or result.stdout).strip().splitlines()
        detail = lines[-1] if lines else "unknown error"
        raise RuntimeError("Douyin download failed: " + detail)
    return target, url


def acquire_douyin_batch(query: str, output_dir: Path, limit: int = 10) -> list[tuple[Path, str]]:
    requested = max(1, int(limit))
    urls = _search_urls(query, limit=requested)
    if not urls:
        raise RuntimeError(f"No public Douyin video URLs were discovered for '{query}'.")
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
    return acquire_douyin_batch(query, output_dir, limit=limit)[0]
