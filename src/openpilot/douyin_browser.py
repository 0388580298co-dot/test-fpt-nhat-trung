from __future__ import annotations

import html
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

from .config import CONFIG

MEDIA_URL_RE = re.compile(r"https?://[^\"'<>\s]+(?:\.mp4|\.m3u8|/play/|playwm)[^\"'<>\s]*", re.I)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"


def _timeout_ms() -> int:
    return CONFIG.browser_timeout_ms


def _chrome_executable() -> str | None:
    candidates = [
        os.getenv("OPENPILOT_CHROME", "").strip(),
        os.getenv("PROGRAMFILES", "") + r"\Google\Chrome\Application\chrome.exe",
        os.getenv("PROGRAMFILES(X86)", "") + r"\Google\Chrome\Application\chrome.exe",
        os.getenv("LOCALAPPDATA", "") + r"\Google\Chrome\Application\chrome.exe",
        os.getenv("PROGRAMFILES", "") + r"\Microsoft\Edge\Application\msedge.exe",
        os.getenv("PROGRAMFILES(X86)", "") + r"\Microsoft\Edge\Application\msedge.exe",
    ]
    for value in candidates:
        if value and Path(value).is_file():
            return value
    return None


def _browser_context(playwright):
    executable = _chrome_executable()
    kwargs = {"headless": True, "timeout": _timeout_ms()}
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


def _prepare_page(page, url: str, limit: int) -> None:
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


def browser_download_video(url: str, output: Path, timeout_ms: int | None = None) -> bool:
    """Capture a real video/mp4 response from a normally rendered public page.

    This avoids the fragile pattern of extracting a signed CDN URL and then
    opening it in a new session. Every browser operation is bounded and the
    response is accepted only when it is actual video bytes.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[DOUYIN-BROWSER] Playwright is not installed", flush=True)
        return False

    limit = timeout_ms or _timeout_ms()
    output.parent.mkdir(parents=True, exist_ok=True)
    captured: list[tuple[str, str, int]] = []
    browser = context = page = None
    try:
        with sync_playwright() as playwright:
            browser, context = _browser_context(playwright)
            page = context.new_page()

            def on_response(response) -> None:
                try:
                    ctype = (response.headers.get("content-type") or "").lower()
                    value = response.url.lower()
                    if "video/mp4" in ctype or ("video/" in ctype and ".m3u8" not in value):
                        length = int(response.headers.get("content-length", "0") or 0)
                        captured.append((response.url, ctype, length))
                except Exception:
                    pass

            page.on("response", on_response)
            _prepare_page(page, url, limit)
            try:
                page.mouse.wheel(0, 700)
            except Exception:
                pass
            page.wait_for_timeout(1_000)

            # Prefer the largest captured MP4. Very small responses are usually
            # posters/thumbnails rather than the actual video.
            candidates = sorted(captured, key=lambda item: item[2], reverse=True)
            print(f"[DOUYIN-BROWSER]   captured video responses: {len(candidates)}", flush=True)
            for media_url, content_type, content_length in candidates[:CONFIG.max_browser_media]:
                if content_length and content_length < 100_000:
                    continue
                try:
                    response = context.request.get(media_url, headers={"Referer": url, "Origin": "https://www.douyin.com", "User-Agent": USER_AGENT, "Accept": "video/mp4,*/*"}, timeout=20_000)
                    status = int(response.status)
                    headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
                    actual_type = headers.get("content-type", content_type)
                    body = response.body()
                    response.dispose()
                    print(f"[DOUYIN-BROWSER]   media response: HTTP {status} | type={actual_type} | bytes={len(body)}", flush=True)
                    if status == 200 and len(body) >= 100_000 and "video/" in actual_type and "mpegurl" not in actual_type:
                        temp = output.with_suffix(output.suffix + ".browser.tmp")
                        temp.write_bytes(body)
                        temp.replace(output)
                        return True
                except Exception as exc:
                    print(f"[DOUYIN-BROWSER]   captured media request failed: {exc}", flush=True)
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
        print("[DOUYIN-BROWSER] Playwright is not installed", flush=True)
        return []
    limit = timeout_ms or _timeout_ms()
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
            _prepare_page(page, url, limit)
            try:
                values = page.evaluate("""
                    () => {
                        const out = [];
                        const add = (v) => { if (v && typeof v === 'string' && v.length < 100000) out.push(v); };
                        document.querySelectorAll('video').forEach(v => {
                            add(v.currentSrc); add(v.src);
                            v.querySelectorAll('source').forEach(s => add(s.src));
                        });
                        for (const entry of performance.getEntriesByType('resource')) {
                            if (entry.name && (entry.name.includes('.mp4') || entry.name.includes('.m3u8') || entry.name.includes('playwm') || entry.name.includes('/play/'))) add(entry.name);
                        }
                        return out;
                    }
                """)
            except Exception as exc:
                print(f"[DOUYIN-BROWSER]   media DOM scan skipped: {exc}", flush=True)
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
    """Download complete public media; reject HTML, playlists and partial data."""
    output.parent.mkdir(parents=True, exist_ok=True)
    request = Request(media_url, headers={
        "User-Agent": USER_AGENT, "Referer": referer, "Origin": "https://www.douyin.com",
        "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
    })
    try:
        with urlopen(request, timeout=CONFIG.download_timeout_s) as response:
            status = getattr(response, "status", response.getcode())
            content_type = (response.headers.get("Content-Type") or "").lower()
            content_range = response.headers.get("Content-Range") or ""
            print(f"[DOUYIN-BROWSER]   direct media: HTTP {status} | type={content_type or '?'} | range={content_range or '-'}", flush=True)
            if status == 200 and not content_range and "video/" in content_type and "mpegurl" not in content_type:
                with output.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                if output.stat().st_size >= 100_000:
                    return True
    except Exception as exc:
        print(f"[DOUYIN-BROWSER]   direct media failed: {exc}", flush=True)
    try:
        output.unlink()
    except FileNotFoundError:
        pass
    return False
