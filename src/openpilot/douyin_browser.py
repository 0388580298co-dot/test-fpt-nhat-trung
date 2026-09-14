from __future__ import annotations

import html
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

MEDIA_URL_RE = re.compile(r"https?://[^\"'<>\\s]+(?:\.mp4|\.m3u8|/play/|playwm)[^\"'<>\\s]*", re.I)


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


def browser_media_urls(url: str, timeout_ms: int = 60000) -> list[str]:
    """Extract media URLs exposed by a normal rendered public Douyin page."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[DOUYIN-BROWSER] Playwright is not installed", flush=True)
        return []

    executable = _chrome_executable()
    captured: list[str] = []
    try:
        with sync_playwright() as playwright:
            kwargs = {"headless": True}
            if executable:
                kwargs["executable_path"] = executable
            browser = playwright.chromium.launch(**kwargs)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
                locale="zh-CN",
            )
            page = context.new_page()

            def on_response(response) -> None:
                try:
                    value = response.url
                    content_type = (response.headers.get("content-type") or "").lower()
                    if ("video/" in content_type or "mpegurl" in content_type or ".mp4" in value.lower() or ".m3u8" in value.lower() or "/play/" in value.lower() or "playwm" in value.lower()):
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
    request = Request(media_url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Referer": referer,
        "Accept": "*/*",
    })
    with urlopen(request, timeout=90) as response, output.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    return output.exists() and output.stat().st_size > 100_000
