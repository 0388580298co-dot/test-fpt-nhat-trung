from __future__ import annotations

import html
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote_plus, unquote
from urllib.request import Request, urlopen

from .douyin_browser import browser_media_urls, download_media

DOUYIN_VIDEO_RE = re.compile(r"https?://(?:www\.)?douyin\.com/video/\d+|https?://jingxuan.douyin.com/m/video/\d+|https?://(?:www\.)?douyin\.com/shipin/\d+|https?://v\.douyin\.com/[A-Za-z0-9_-]+/?")
DOUYIN_ID_RE = re.compile(r"(?:aweme_id|awemeId|itemId|item_id|video_id)[\"'=: ]+([0-9]{8,30})")

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


def _is_valid_video(path: Path) -> bool:
    """Reject HTML/JSON/partial CDN chunks saved with an .mp4 extension."""
    if not path.exists() or path.stat().st_size < 100_000:
        return False
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=format_name,duration",
                "-show_entries", "stream=codec_type,codec_name,width,height",
                "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    text = result.stdout or ""
    return '"codec_type": "video"' in text and '"duration"' in text


def _discard_invalid_video(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _extract_urls(page: str, limit: int) -> list[str]:
    page = unquote(html.unescape(page)).replace(r"\/", "/").replace(r"\u002F", "/").replace(r"\u002f", "/")
    found: list[str] = []
    for url in DOUYIN_VIDEO_RE.findall(page):
        url = url.rstrip(".,);\"'")
        if url not in found:
            found.append(url)
        if len(found) >= limit:
            return found
    for video_id in DOUYIN_ID_RE.findall(page):
        url = f"https://www.douyin.com/video/{video_id}"
        if url not in found:
            found.append(url)
        if len(found) >= limit:
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
    return list(dict.fromkeys(x for x in [clean, " ".join(words[:8]), "Vietnam", "越南", "越南 热门", "热点 新闻", "热门 视频", "抖音 热门", "今日热点"] if x))


def _search_engine_urls(query: str, limit: int) -> list[str]:
    found: list[str] = []
    for term in _query_variants(query):
        for search in (f"site:douyin.com/video {term}", f"site:jingxuan.douyin.com/m/video {term}"):
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
    pages = ["https://www.douyin.com/shipin/", "https://www.douyin.com/hot", "https://jingxuan.douyin.com/", f"https://www.douyin.com/search/?type=video&keyword={quote_plus(query)}"]
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
    for url in PUBLIC_DOYIN_SEEDS:
        if url not in found:
            found.append(url)
        if len(found) >= candidate_limit:
            break
    return found[:candidate_limit]


def _chrome_profile_available() -> bool:
    local = os.getenv("LOCALAPPDATA", "")
    appdata = os.getenv("APPDATA", "")
    return any((Path(p) / "User Data").is_dir() for p in (
        Path(local) / "Google" / "Chrome",
        Path(appdata) / "Google" / "Chrome",
    ))


def _run_ytdlp(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False, timeout=240)
    except FileNotFoundError:
        command[0:1] = [os.environ.get("PYTHON", "python"), "-m", "yt_dlp"]
        return subprocess.run(command, capture_output=True, text=True, check=False, timeout=240)


def _download_public_url(url: str, output_dir: Path, index: int) -> tuple[Path, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"douyin-{index:02d}.mp4"
    base = ["yt-dlp", "--no-playlist", "--format", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b", "--merge-output-format", "mp4", "--output", str(target)]
    cookies = os.getenv("OPENPILOT_DOUYIN_COOKIES", "").strip()
    if cookies:
        cookie_path = Path(cookies).expanduser()
        if not cookie_path.is_file():
            raise RuntimeError(f"Douyin cookie file not found: {cookie_path}")
        base.extend(["--cookies", str(cookie_path)])
    base.append(url)

    print("[DOUYIN]   Direct public download...", flush=True)
    result = _run_ytdlp(base)
    if result.returncode == 0 and target.exists() and _is_valid_video(target):
        return target, url
    if target.exists():
        print("[DOUYIN]   Direct download produced an invalid/partial MP4 -> discard", flush=True)
        _discard_invalid_video(target)
    direct_error = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()

    if not cookies and _chrome_profile_available():
        print("[DOUYIN]   Direct download failed -> trying Chrome cookies...", flush=True)
        for profile in ("Default", "Profile 1", "Profile 2"):
            browser_command = base[:-1] + ["--cookies-from-browser", f"chrome:{profile}", url]
            browser_result = _run_ytdlp(browser_command)
            if browser_result.returncode == 0 and target.exists() and _is_valid_video(target):
                return target, url
            if target.exists():
                _discard_invalid_video(target)
            print(f"[DOUYIN]   Chrome {profile}: unavailable/failed", flush=True)

    print("[DOUYIN]   Trying rendered Douyin browser media...", flush=True)
    media_urls = browser_media_urls(url)
    print(f"[DOUYIN]   Browser media candidates: {len(media_urls)}", flush=True)
    for media_number, media_url in enumerate(media_urls[:8], 1):
        try:
            print(f"[DOUYIN]   Browser media {media_number}/{min(len(media_urls), 8)}...", flush=True)
            if download_media(media_url, target, url):
                if _is_valid_video(target):
                    return target, url
                print("[DOUYIN]   Browser media returned bytes, but ffprobe rejected the file -> discard", flush=True)
                _discard_invalid_video(target)
        except Exception as exc:
            print(f"[DOUYIN]   Browser media failed: {exc}", flush=True)
            _discard_invalid_video(target)
            continue

    if media_urls:
        raise RuntimeError("Browser exposed media URLs, but no complete playable video could be downloaded")
    if "Extracting cookies from edge" in direct_error:
        raise RuntimeError("No browser-exposed public media URL found (Edge cookie fallback skipped)")
    lines = direct_error.splitlines()
    detail = lines[-1] if lines else "no public media URL available"
    raise RuntimeError("No browser-exposed public media URL found; yt-dlp: " + detail)


def acquire_douyin_batch(query: str, output_dir: Path, limit: int = 10) -> list[tuple[Path, str]]:
    requested = max(1, int(limit))
    print(f"[DOUYIN] Search query: {query}", flush=True)
    urls = _search_urls(query, limit=requested)
    if not urls:
        raise RuntimeError(f"No public Douyin video URLs were discovered for '{query}'.")
    successes: list[tuple[Path, str]] = []
    errors: list[str] = []
    print(f"[DOUYIN] Candidates found: {len(urls)} | Target: {requested}", flush=True)
    for index, url in enumerate(urls, 1):
        if len(successes) >= requested:
            break
        print(f"[DOUYIN] Trying {index}/{len(urls)} | downloaded={len(successes)}/{requested}", flush=True)
        try:
            item = _download_public_url(url, output_dir, len(successes) + 1)
            successes.append(item)
            print(f"[DOUYIN]   OK  {item[0].name} | total={len(successes)}/{requested}", flush=True)
        except Exception as exc:
            errors.append(str(exc))
            print(f"[DOUYIN]   SKIP {exc}", flush=True)
    print(f"[DOUYIN] Result: {len(successes)}/{requested} downloaded", flush=True)
    if not successes:
        detail = errors[-1] if errors else "all discovered URLs were inaccessible"
        raise RuntimeError(f"No accessible public Douyin video found for '{query}'. {detail}")
    return successes


def acquire_douyin(query: str, output_dir: Path, limit: int = 10) -> tuple[Path, str]:
    return acquire_douyin_batch(query, output_dir, limit=limit)[0]
