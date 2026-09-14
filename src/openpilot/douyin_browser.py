from __future__ import annotations

import html
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

from .config import CONFIG

MEDIA_URL_RE = re.compile(r"https?://[^\"'<>\s]+(?:\.mp4|\.m3u8|/play/|playwm)[^\"'<>\s]*", re.I)
CONTENT_RANGE_RE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", re.I)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
MIN_MEDIA_BYTES = 100_000
RANGE_CHUNK_BYTES = 4 * 1024 * 1024


def _chrome_executable() -> str | None:
    candidates = [
        os.getenv("OPENPILOT_CHROME", "").strip(),
        os.getenv("PROGRAMFILES", "") + r"\Google\Chrome\Application\chrome.exe",
        os.getenv("PROGRAMFILES(X86)", "") + r"\Google\Chrome\Application\chrome.exe",
        os.getenv("LOCALAPPDATA", "") + r"\Google\Chrome\Application\chrome.exe",
        os.getenv("PROGRAMFILES", "") + r"\Microsoft\Edge\Application\msedge.exe",
        os.getenv("PROGRAMFILES(X86)", "") + r"\Microsoft\Edge\Application\msedge.exe",
    ]
    return next((value for value in candidates if value and Path(value).is_file()), None)


def _browser_context(playwright):
    executable = _chrome_executable()
    kwargs = {"headless": True, "timeout": CONFIG.browser_timeout_ms}
    if executable:
        kwargs["executable_path"] = executable
    browser = playwright.chromium.launch(**kwargs)
    context = browser.new_context(
        user_agent=USER_AGENT,
        locale="zh-CN",
        extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
    )
    return browser, context


def _normalise_urls(values: list[str]) -> list[str]:
    found: list[str] = []
    for value in values:
        value = html.unescape(value).replace(r"\/", "/").replace(r"\u002F", "/").replace(r"\u002f", "/")
        for item in MEDIA_URL_RE.findall(value):
            item = item.rstrip("\\\"'<>),;]")
            if item not in found:
                found.append(item)
    return found


def _prepare_page(page, url: str) -> None:
    limit = CONFIG.browser_timeout_ms
    page.set_default_timeout(min(limit, 12_000))
    page.set_default_navigation_timeout(limit)
    print(f"[DOUYIN-BROWSER]   opening page (timeout={limit / 1000:.0f}s)...", flush=True)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=limit)
    except Exception as exc:
        print(f"[DOUYIN-BROWSER]   page open stopped: {exc}", flush=True)
    page.wait_for_timeout(CONFIG.browser_settle_ms)
    try:
        page.locator("video").first.evaluate("""v => { v.muted = true; const p = v.play(); if (p) p.catch(() => {}); }""")
    except Exception:
        pass
    page.wait_for_timeout(CONFIG.browser_settle_ms)


def _parse_content_range(value: str) -> tuple[int, int, int | None] | None:
    match = CONTENT_RANGE_RE.fullmatch(value.strip())
    if not match:
        return None
    start, end, total = match.groups()
    return int(start), int(end), None if total == "*" else int(total)


def _valid_video_body(body: bytes) -> bool:
    if len(body) < MIN_MEDIA_BYTES:
        return False
    head = body[:64].lower()
    if b"ftyp" in head:
        return True
    return body[:4] in {b"\x00\x00\x00\x18", b"\x00\x00\x00\x20", b"\x00\x00\x00\x1c"}


def _download_range(url: str, start: int, end: int, referer: str) -> tuple[int, int, bytes, int | None]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": referer,
            "Origin": "https://www.douyin.com",
            "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
            "Range": f"bytes={start}-{end}",
        },
    )
    with urlopen(request, timeout=CONFIG.download_timeout_s) as response:
        status = getattr(response, "status", response.getcode())
        ctype = (response.headers.get("Content-Type") or "").lower()
        if "video/" not in ctype and "mp4" not in ctype:
            raise RuntimeError(f"unexpected media type: {ctype or '?'}")
        body = response.read()
        parsed = _parse_content_range(response.headers.get("Content-Range") or "")
        if status == 200:
            return status, 0, body, len(body)
        if status != 206 or parsed is None:
            raise RuntimeError(f"expected HTTP 206 range response, got {status}")
        actual_start, actual_end, total = parsed
        if actual_start != start or actual_end < actual_start:
            raise RuntimeError(f"server returned unexpected range {actual_start}-{actual_end}")
        return status, actual_end, body, total


def download_media(media_url: str, output: Path, referer: str) -> bool:
    """Download one complete public MP4 URL, including HTTP 206 range responses."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".download.tmp")
    temp.unlink(missing_ok=True)
    try:
        probe_end = RANGE_CHUNK_BYTES - 1
        status, actual_end, body, total = _download_range(media_url, 0, probe_end, referer)
        print(
            f"[DOUYIN-BROWSER]   media fetch: HTTP {status} | first-bytes={len(body)} | total={total or '-'}",
            flush=True,
        )
        if status == 200:
            if len(body) < MIN_MEDIA_BYTES or not _valid_video_body(body):
                raise RuntimeError("full response is not a valid MP4 body")
            temp.write_bytes(body)
        else:
            if total is None or total <= actual_end + 1:
                raise RuntimeError("206 response did not expose a complete file size")
            with temp.open("wb") as handle:
                handle.write(body)
                position = actual_end + 1
                while position < total:
                    requested_end = min(total - 1, position + RANGE_CHUNK_BYTES - 1)
                    next_status, next_end, next_body, next_total = _download_range(media_url, position, requested_end, referer)
                    if next_status != 206 or next_total not in (None, total):
                        raise RuntimeError("inconsistent HTTP range response")
                    expected = next_end - position + 1
                    if len(next_body) != expected:
                        raise RuntimeError(f"short range body: expected {expected}, got {len(next_body)}")
                    handle.write(next_body)
                    position = next_end + 1
                    print(f"[DOUYIN-BROWSER]   range download: {position}/{total} bytes", flush=True)
            if temp.stat().st_size != total:
                raise RuntimeError(f"assembled file size mismatch: {temp.stat().st_size}/{total}")
            if not _valid_video_body(temp.read_bytes()[:64 + MIN_MEDIA_BYTES]):
                raise RuntimeError("assembled body does not look like MP4")

        if temp.stat().st_size < MIN_MEDIA_BYTES:
            raise RuntimeError("downloaded media is too small")
        temp.replace(output)
        return True
    except Exception as exc:
        print(f"[DOUYIN-BROWSER]   media download failed: {exc}", flush=True)
        temp.unlink(missing_ok=True)
        output.unlink(missing_ok=True)
        return False


def browser_download_video(url: str, output: Path, timeout_ms: int | None = None) -> bool:
    """Render a public Douyin page, capture media URLs, then download the complete file.

    We intentionally do not call Playwright Response.body(). Douyin commonly serves
    HTML5 video as HTTP 206 byte ranges, and keeping Response objects until after
    navigation can make their bodies unavailable. We only collect the media URL and
    immediately perform a normal HTTP range download outside the browser.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[DOUYIN-BROWSER] Playwright is not installed", flush=True)
        return False

    output.parent.mkdir(parents=True, exist_ok=True)
    limit = timeout_ms or CONFIG.browser_timeout_ms
    browser = context = None
    candidates: list[tuple[int, str, int, str, str]] = []

    try:
        with sync_playwright() as playwright:
            browser, context = _browser_context(playwright)
            page = context.new_page()
            page.set_default_timeout(min(limit, 12_000))
            page.set_default_navigation_timeout(limit)

            def on_finished(request) -> None:
                if len(candidates) >= CONFIG.max_browser_media:
                    return
                try:
                    response = request.response()
                    if response is None:
                        return
                    ctype = (response.headers.get("content-type") or "").lower()
                    if "video/mp4" not in ctype and not ctype.startswith("video/"):
                        return
                    value = response.url
                    if not value.startswith(("http://", "https://")):
                        return
                    content_range = response.headers.get("content-range") or "-"
                    content_length = int(response.headers.get("content-length", "0") or 0)
                    if content_length and content_length > CONFIG.max_browser_media_bytes:
                        return
                    print(
                        f"[DOUYIN-BROWSER]   media response: HTTP {response.status} | type={ctype} | "
                        f"length={content_length or '-'} | range={content_range}",
                        flush=True,
                    )
                    score = content_length
                    if content_range != "-":
                        parsed = _parse_content_range(content_range)
                        if parsed:
                            score = max(score, parsed[2] or 0)
                    candidates.append((score, value, response.status, ctype, content_range))
                except Exception as exc:
                    print(f"[DOUYIN-BROWSER]   media candidate skipped: {exc}", flush=True)

            page.on("requestfinished", on_finished)
            _prepare_page(page, url)
            try:
                page.mouse.wheel(0, 800)
            except Exception:
                pass
            page.wait_for_timeout(750)
            print(f"[DOUYIN-BROWSER]   captured media URLs: {len(candidates)}", flush=True)

            # Navigation and browser cleanup happen after this block. The URLs
            # are copied as plain strings, so no Playwright Response object is
            # retained and no response.body() call can race with navigation.
            candidates.sort(key=lambda item: item[0], reverse=True)
            candidate_urls = [item[1] for item in candidates]
            referer = page.url or url

        for media_url in candidate_urls:
            if download_media(media_url, output, referer):
                print(f"[DOUYIN-BROWSER]   saved complete browser media: {output.stat().st_size} bytes", flush=True)
                return True
        return False
    except Exception as exc:
        print(f"[DOUYIN-BROWSER] Browser error (bounded): {exc}", flush=True)
        return False
    finally:
        try:
            if context:
                context.close()
        except Exception:
            pass
        try:
            if browser:
                browser.close()
        except Exception:
            pass


def browser_media_urls(url: str, timeout_ms: int | None = None) -> list[str]:
    """Extract media URLs from a normally rendered public Douyin page."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []
    limit = timeout_ms or CONFIG.browser_timeout_ms
    captured: list[str] = []
    values: list[str] = []
    browser = context = None
    try:
        with sync_playwright() as playwright:
            browser, context = _browser_context(playwright)
            page = context.new_page()

            def on_response(response) -> None:
                try:
                    ctype = (response.headers.get("content-type") or "").lower()
                    value = response.url
                    if "video/" in ctype or ".mp4" in value.lower() or ".m3u8" in value.lower() or "/play/" in value.lower() or "playwm" in value.lower():
                        if value not in captured:
                            captured.append(value)
                except Exception:
                    pass

            page.on("response", on_response)
            _prepare_page(page, url)
            try:
                values = page.evaluate("""
                    () => {
                        const out = [];
                        const add = v => { if (v && typeof v === 'string' && v.length < 100000) out.push(v); };
                        document.querySelectorAll('video').forEach(v => { add(v.currentSrc); add(v.src); v.querySelectorAll('source').forEach(s => add(s.src)); });
                        for (const entry of performance.getEntriesByType('resource')) {
                            if (entry.name && (entry.name.includes('.mp4') || entry.name.includes('.m3u8') || entry.name.includes('playwm') || entry.name.includes('/play/'))) add(entry.name);
                        }
                        return out;
                    }
                """)
            except Exception:
                pass
    except Exception as exc:
        print(f"[DOUYIN-BROWSER] Browser error (bounded): {exc}", flush=True)
    finally:
        try:
            if context:
                context.close()
        except Exception:
            pass
        try:
            if browser:
                browser.close()
        except Exception:
            pass
    return _normalise_urls(captured + values)
