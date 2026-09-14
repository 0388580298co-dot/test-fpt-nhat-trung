from __future__ import annotations

import importlib.util
import os
import shutil
import urllib.request


def _check_command(name: str) -> tuple[bool, str]:
    path = shutil.which(name)
    return (bool(path), path or "not found")


def _check_ollama() -> tuple[bool, str]:
    url = os.getenv("OPENPILOT_OLLAMA_URL", "http://127.0.0.1:11434/api/tags")
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return True, f"HTTP {response.status}"
    except Exception as exc:
        return False, str(exc)


def run_doctor() -> int:
    print("\nOPENPILOT STUDIO - SYSTEM DIAGNOSTICS\n" + "=" * 58)
    checks: list[tuple[str, bool, str]] = []
    for command in ("ffmpeg", "ffprobe", "yt-dlp"):
        ok, detail = _check_command(command)
        checks.append((command, ok, detail))
    for module in ("faster_whisper", "pyttsx3", "playwright"):
        ok = importlib.util.find_spec(module) is not None
        checks.append((module, ok, "installed" if ok else "not installed"))
    if os.getenv("OPENPILOT_AI_PROVIDER", "local").lower() == "local":
        ok, detail = _check_ollama()
        checks.append(("ollama", ok, detail))

    for name, ok, detail in checks:
        print(f"  {'OK' if ok else 'FAIL':<4} {name:<18} {detail}")
    print("=" * 58)
    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print("Missing/failed checks: " + ", ".join(failed))
        return 1
    print("System is ready for OpenPilot AUTO.")
    return 0
