"""Read-only GitHub repository inspection tools."""
from __future__ import annotations

import json
from urllib.request import Request, urlopen


def _get_json(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "OpenPilot/0.2"})
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_repo_url(value: str) -> tuple[str, str]:
    value = value.strip().rstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    parts = [p for p in value.split("/") if p]
    if len(parts) < 2:
        raise ValueError("Expected a GitHub repository like owner/repo")
    return parts[0], parts[1].removesuffix(".git")


def inspect_repository(repo: str) -> dict:
    owner, name = parse_repo_url(repo)
    data = _get_json(f"https://api.github.com/repos/{owner}/{name}")
    return {
        "full_name": data["full_name"],
        "description": data.get("description"),
        "default_branch": data.get("default_branch"),
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "open_issues": data.get("open_issues_count", 0),
        "language": data.get("language"),
        "license": (data.get("license") or {}).get("spdx_id"),
        "url": data.get("html_url"),
    }
