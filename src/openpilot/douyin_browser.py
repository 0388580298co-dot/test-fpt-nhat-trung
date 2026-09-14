from __future__ import annotations

import html
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

MEDIA_URL_RE = re.compile(r"https?://[^\"'<>\s]+(?:\.mp4|\.m3u8|/play/|playwm)[^\"'<>\s]*", re.I)
VIDEO_TYPES = ("video/", "application/octet-stream")


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
                page.locator("video").first.evaluate("""v => { v.muted = true; return v.play().catch(() => false); }""")
                page.wait_for_timeout(5000)
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


def _write_full_response(response, output: Path) -> bool:
    status = int(response.status)
    headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
    content_type = headers.get("content-type", "").lower()
    content_range = headers.get("content-range", "")
    content_length = headers.get("content-length", "")
    print(
        f"[DOUYIN-BROWSER]   media response: HTTP {status} | type={content_type or '?'} | length={content_length or '?'} | range={content_range or '-'}",
        flush=True,
    )

    # Never save HTML, JSON, HLS playlists, or a single byte-range chunk as .mp4.
    if "text/html" in content_type or "application/json" in content_type or "mpegurl" in content_type or "\.m3u8" in content_type:
        return False
    if status != 200 or content_range:
        return False

    body = response.body()
    if len(body) < 100_000:
        return False
    output.write_bytes(body)
    return True


def _download_browser_full_or_ranges(context, media_url: str, output: Path, referer: str, user_agent: str) -> bool:
    common_headers = {
        "Referer": referer,
        "Origin": "https://www.douyin.com",
        "User-Agent": user_agent,
        "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
    }
    response = context.request.get(media_url, headers=common_headers, timeout=90000)
    status = int(response.status)
    headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
    content_type = headers.get("content-type", "").lower()
    content_range = headers.get("content-range", "")
    content_length = headers.get("content-length", "")
    print(
        f"[DOUYIN-BROWSER]   browser request: HTTP {status} | type={content_type or '?'} | length={content_length or '?'} | range={content_range or '-'}",
        flush=True,
    )

    if "text/html" in content_type or "application/json" in content_type or "mpegurl" in content_type:
        response.dispose()
        return False

    if status == 200 and not content_range:
        body = response.body()
        response.dispose()
        if len(body) >= 100_000:
            output.write_bytes(body)
            return True
        return False

    # Douyin/CDN may require byte-range requests. Assemble the complete file
    # only when the server explicitly tells us the total size.
    if status != 206 or not content_range:
        response.dispose()
        return False
    match = re.match(r"bytes\s+(\d+)-(\d+)/(\d+)", content_range)
    if not match:
        response.dispose()
        return False
    start, end, total = map(int, match.groups())
    first = response.body()
    response.dispose()
    if start != 0 or end < start or total <= end or len(first) != end - start + 1:
        return False

    temp = output.with_suffix(output.suffix + ".partial")
    try:
        with temp.open("wb") as handle:
            handle.write(first)
            offset = end + 1
            chunk_size = 2 * 1024 * 1024
            while offset < total:
                chunk_end = min(total - 1, offset + chunk_size - 1)
                part = context.request.get(
                    media_url,
                    headers={**common_headers, "Range": f"bytes={offset}-{chunk_end}"},
                    timeout=90000,
                )
                part_status = int(part.status)
                part_headers = {str(k).lower(): str(v) for k, v in part.headers.items()}
                part_range = part_headers.get("content-range", "")
                body = part.body()
                part.dispose()
                expected = chunk_end - offset + 1
                if part_status != 206 or len(body) != expected or not re.match(rf"bytes\s+{offset}-{chunk_end}/", part_range):
                    print(f"[DOUYIN-BROWSER]   range download stopped at {offset}/{total}: HTTP {part_status} range={part_range or '-'} bytes={len(body)} expected={expected}", flush=True)
                    return False
                handle.write(body)
                offset = chunk_end + 1
        if temp.stat().st_size != total or total < 100_000:
            return False
        temp.replace(output)
        return True
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def download_media(media_url: str, output: Path, referer: str) -> bool:
    """Download complete public media; reject partial CDN chunks masquerading as MP4."""
    output.parent.mkdir(parents=True, exist_ok=True)
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"

    # First try a normal full HTTP response.
    request = Request(media_url, headers={
        "User-Agent": user_agent,
        "Referer": referer,
        "Origin": "https://www.douyin.com",
        "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
    })
    try:
        with urlopen(request, timeout=90) as response:
            status = getattr(response, "status", response.getcode())
            content_type = (response.headers.get("Content-Type") or "").lower()
            content_range = response.headers.get("Content-Range") or ""
            print(f"[DOUYIN-BROWSER]   direct media: HTTP {status} | type={content_type or '?'} | range={content_range or '-'}", flush=True)
            if status == 200 and not content_range and "text/html" not in content_type and "application/json" not in content_type and "mpegurl" not in content_type:
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
            try:
                page.locator("video").first.evaluate("""v => { v.muted = true; return v.play().catch(() => false); }""")
                page.wait_for_timeout(4000)
            except Exception:
                pass
            ok = _download_browser_full_or_ranges(context, media_url, output, referer, user_agent)
            browser.close()
            if ok:
                return True
    except Exception as exc:
        print(f"[DOUYIN-BROWSER] Browser-session download failed: {exc}", flush=True)
    try:
        output.unlink()
    except FileNotFoundError:
        pass
    return False
