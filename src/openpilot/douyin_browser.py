from __future__ import annotations

import html
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

from .config import CONFIG

MEDIA_URL_RE = re.compile(r"https?://[^\"'<>\s]+(?:\.mp4|\.m3u8|/play/|playwm)[^\"'<>\s]*", re.I)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
MIN_MEDIA_BYTES = 100_000


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


def _valid_video_body(body: bytes) -> bool:
    if len(body) < MIN_MEDIA_BYTES:
        return False
    head = body[:64].lower()
    # MP4 normally has an ftyp box near the beginning. Accept a small
    # amount of leading data because some CDNs prepend metadata.
    if b"ftyp" in head:
        return True
    # A response can still be a valid MP4 even when the first bytes are not
    # available in the captured range. Let ffprobe perform the final check.
    return body[:4] in {b"\x00\x00\x00\x18", b"\x00\x00\x00\x20", b"\x00\x00\x00\x1c"}


def browser_download_video(url: str, output: Path, timeout_ms: int | None = None) -> bool:
    """Capture a complete-enough public MP4 response from the rendered page.

    Important: the old implementation collected Response objects and called
    response.body() only after navigation had already moved on. Playwright
    can then report that the body is no longer available. We now consume the
    response body from requestfinished, while the response is still attached
    to the active request lifecycle. This also removes the unbounded wait that
    caused AUTO to appear frozen on candidate 12/12.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[DOUYIN-BROWSER] Playwright is not installed", flush=True)
        return False

    output.parent.mkdir(parents=True, exist_ok=True)
    limit = timeout_ms or CONFIG.browser_timeout_ms
    browser = context = None
    captured: list[tuple[int, int, bytes]] = []
    capture_deadline = None

    try:
        with sync_playwright() as playwright:
            browser, context = _browser_context(playwright)
            page = context.new_page()
            page.set_default_timeout(min(limit, 12_000))
            page.set_default_navigation_timeout(limit)

            def on_finished(request) -> None:
                if len(captured) >= CONFIG.max_browser_media:
                    return
                try:
                    response = request.response()
                    if response is None:
                        return
                    ctype = (response.headers.get("content-type") or "").lower()
                    if "video/mp4" not in ctype and not ctype.startswith("video/"):
                        return
                    content_range = response.headers.get("content-range") or "-"
                    content_length = int(response.headers.get("content-length", "0") or 0)
                    print(
                        f"[DOUYIN-BROWSER]   media response: HTTP {response.status} | type={ctype} | "
                        f"length={content_length or '-'} | range={content_range}",
                        flush=True,
                    )
                    if content_length and content_length < MIN_MEDIA_BYTES:
                        return
                    # requestfinished means the response body has finished
                    # downloading; read it immediately before navigation can
                    # detach the resource from the page.
                    body = response.body()
                    if _valid_video_body(body):
                        captured.append((response.status, len(body), body))
                except Exception as exc:
                    print(f"[DOUYIN-BROWSER]   media capture skipped: {exc}", flush=True)

            page.on("requestfinished", on_finished)
            _prepare_page(page, url)
            try:
                page.mouse.wheel(0, 800)
            except Exception:
                pass
            page.wait_for_timeout(750)
            print(f"[DOUYIN-BROWSER]   captured usable video responses: {len(captured)}", flush=True)

            # Prefer the largest response. A 206 response is acceptable here:
            # ffprobe is the final authority on whether the captured bytes form
            # a playable video, and the acquisition layer rejects short videos.
            if captured:
                captured.sort(key=lambda item: item[1], reverse=True)
                for status, size, body in captured:
                    if status not in (200, 206) or size < MIN_MEDIA_BYTES:
                        continue
                    temp = output.with_suffix(output.suffix + ".browser.tmp")
                    temp.write_bytes(body)
                    temp.replace(output)
                    print(f"[DOUYIN-BROWSER]   saved browser media: {size} bytes", flush=True)
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


def download_media(media_url: str, output: Path, referer: str) -> bool:
    """Download one complete public MP4 URL; never accept partial/HTML data."""
    output.parent.mkdir(parents=True, exist_ok=True)
    request = Request(
        media_url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": referer,
            "Origin": "https://www.douyin.com",
            "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=CONFIG.download_timeout_s) as response:
            status = getattr(response, "status", response.getcode())
            ctype = (response.headers.get("Content-Type") or "").lower()
            print(
                f"[DOUYIN-BROWSER]   direct media: HTTP {status} | type={ctype or '?'} | "
                f"range={response.headers.get('Content-Range') or '-'}",
                flush=True,
            )
            if status == 200 and "video/" in ctype and "mpegurl" not in ctype and not response.headers.get("Content-Range"):
                with output.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                if output.stat().st_size >= MIN_MEDIA_BYTES:
                    return True
    except Exception as exc:
        print(f"[DOUYIN-BROWSER]   direct media failed: {exc}", flush=True)
    output.unlink(missing_ok=True)
    return False
