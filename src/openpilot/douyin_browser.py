from __future__ import annotations

import html
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

MEDIA_URL_RE = re.compile(r"https?://[^\"'<>\\s]+(?:\.mp4|\.m3u8)[^\"'<>\\s]*", re.I)


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


def browser_media_urls(url: str, timeout_ms: int = 45000) -> list[str]:
    """Extract media URLs from the normal rendered public Douyin page.

    This fallback exists because the current yt-dlp Douyin extractor can fail
    with "Fresh cookies" even for public videos. It does not solve CAPTCHAs,
    bypass access controls, or call private APIs.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    executable = _chrome_executable()
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
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(5000)
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
                            if (value && (value.includes('.mp4') || value.includes('.m3u8') || value.includes('playwm') || value.includes('play/'))) add(value);
                        }
                    });
                    add(document.documentElement.innerHTML);
                    return out;
                }
            """)
            browser.close()
    except Exception:
        return []

    found: list[str] = []
    for value in values:
        value = html.unescape(value).replace(r"\/", "/").replace(r"\u002F", "/")
        matches = MEDIA_URL_RE.findall(value)
        if not matches and value.startswith("http") and ("/play/" in value or "playwm" in value):
            matches = [value]
        for item in matches:
            item = item.rstrip("\\\"'<>),;")
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
