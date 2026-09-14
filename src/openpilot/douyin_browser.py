from __future__ import annotations

import html
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

MEDIA_URL_RE = re.compile(r"https?://[^\"'<>\s]+(?:\.mp4|\.m3u8|/play/|playwm)[^\"'<>\s]*", re.I)


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
    kwargs = {"headless": True}
    if executable:
        kwargs["executable_path"] = executable
    browser = playwright.chromium.launch(**kwargs)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        locale="zh-CN",
        extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
    )
    return browser, context


def browser_media_urls(url: str, timeout_ms: int = 60000) -> list[str]:
    """Extract media URLs exposed by a normal rendered public Douyin page."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[DOUYIN-BROWSER] Playwright is not installed", flush=True)
        return []

    captured: list[str] = []
    values: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser, context = _browser_context(playwright)
            page = context.new_page()

            def on_response(response) -> None:
                try:
                    value = response.url
                    content_type = (response.headers.get("content-type") or "").lower()
                    if (
                        "video/" in content_type
                        or "mpegurl" in content_type
                        or ".mp4" in value.lower()
                        or ".m3u8" in value.lower()
                        or "/play/" in value.lower()
                        or "playwm" in value.lower()
                    ):
                        captured.append(value)
                except Exception:
                    pass

            page.on("response", on_response)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(8000)
            try:
                page.mouse.wheel(0, 900)
                page.wait_for_timeout(3000)
            except Exception:
                pass

            values = page.evaluate("""
                () => {
                    const out = [];
                    const add = (v) => { if (v && typeof v === 'string') out.push(v); };
                    document.querySelectorAll('video').forEach(v => {
                        add(v.currentSrc); add(v.src);
                        v.querySelectorAll('source').forEach(s => add(s.src));
                    });
                    document.querySelectorAll('[src], [data-src], [data-url], [href]').forEach(el => {
                        for (const key of ['src', 'data-src', 'data-url', 'href']) {
                            const value = el.getAttribute(key);
                            if (value && (value.includes('.mp4') || value.includes('.m3u8') || value.includes('playwm') || value.includes('/play/'))) add(value);
                        }
                    });
                    for (const entry of performance.getEntriesByType('resource')) add(entry.name);
                    add(document.documentElement.innerHTML);
                    return out;
                }
            """)
            browser.close()
    except Exception as exc:
        print(f"[DOUYIN-BROWSER] Browser error: {exc}", flush=True)
        return []

    found: list[str] = []
    for value in list(captured) + list(values):
        value = html.unescape(value).replace(r"\/", "/").replace(r"\u002F", "/")
        for item in MEDIA_URL_RE.findall(value):
            item = item.rstrip("\\\"'<>),;]")
            if item not in found:
                found.append(item)
    return found


def download_media(media_url: str, output: Path, referer: str) -> bool:
    """Download public media, retrying inside the same kind of browser session used to discover it."""
    output.parent.mkdir(parents=True, exist_ok=True)
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
    request = Request(media_url, headers={
        "User-Agent": user_agent,
        "Referer": referer,
        "Origin": "https://www.douyin.com",
        "Accept": "*/*",
    })
    try:
        with urlopen(request, timeout=90) as response, output.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        if output.exists() and output.stat().st_size > 100_000:
            return True
        try:
            output.unlink()
        except FileNotFoundError:
            pass
    except Exception:
        try:
            output.unlink()
        except FileNotFoundError:
            pass

    # Some public Douyin media URLs are valid only with the browser session
    # that opened the page. Re-open the public page and request the media
    # through that same Playwright context, without solving CAPTCHAs or
    # bypassing access controls.
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False

    try:
        with sync_playwright() as playwright:
            browser, context = _browser_context(playwright)
            page = context.new_page()
            page.goto(referer, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(7000)
            response = context.request.get(
                media_url,
                headers={
                    "Referer": referer,
                    "Origin": "https://www.douyin.com",
                    "User-Agent": user_agent,
                    "Accept": "*/*",
                },
                timeout=90000,
            )
            if response.ok:
                body = response.body()
                if len(body) > 100_000:
                    output.write_bytes(body)
                    browser.close()
                    return True
            response.dispose()
            browser.close()
    except Exception as exc:
        print(f"[DOUYIN-BROWSER] Browser-session download failed: {exc}", flush=True)
    return False
