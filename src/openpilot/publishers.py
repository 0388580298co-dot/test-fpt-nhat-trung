from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class PublishResult:
    platform: str
    status: str
    external_id: str | None = None
    message: str = ""


class Publisher(Protocol):
    def publish(self, video_path: str, title: str, description: str = "") -> PublishResult: ...


class ManualPublisher:
    """Dry-run publisher used until an official platform API is configured."""

    def __init__(self, platform: str):
        self.platform = platform

    def publish(self, video_path: str, title: str, description: str = "") -> PublishResult:
        return PublishResult(self.platform, "dry_run", message="No platform API configured; nothing was uploaded.")
