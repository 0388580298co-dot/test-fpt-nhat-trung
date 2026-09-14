from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path


def _request(url: str, token: str, payload: dict, method: str = "POST") -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode())


def publish_tiktok(video_path: str, title: str) -> str:
    token = os.getenv("TIKTOK_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Missing TIKTOK_ACCESS_TOKEN.")
    path = Path(video_path)
    size = path.stat().st_size
    chunk = min(size, 10 * 1024 * 1024)
    init = _request("https://open.tiktokapis.com/v2/post/publish/video/init/", token, {
        "post_info": {"title": title[:2200], "privacy_level": os.getenv("TIKTOK_PRIVACY", "SELF_ONLY"), "disable_duet": False, "disable_comment": False, "disable_stitch": False, "is_aigc": True},
        "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk, "total_chunk_count": (size + chunk - 1) // chunk},
    })
    upload_url = init["data"]["upload_url"]
    with path.open("rb") as f:
        offset = 0
        while offset < size:
            data = f.read(chunk)
            end = offset + len(data) - 1
            req = urllib.request.Request(upload_url, data=data, headers={"Content-Type": "video/mp4", "Content-Length": str(len(data)), "Content-Range": f"bytes {offset}-{end}/{size}"}, method="PUT")
            with urllib.request.urlopen(req, timeout=180):
                pass
            offset = end + 1
    return init["data"]["publish_id"]


def publish_youtube(video_path: str, title: str, description: str = "") -> str:
    token = os.getenv("YOUTUBE_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Missing YOUTUBE_ACCESS_TOKEN.")
    boundary = "OpenPilotBoundary"
    metadata = {"snippet": {"title": title[:100], "description": description}, "status": {"privacyStatus": os.getenv("YOUTUBE_PRIVACY", "private"), "selfDeclaredMadeForKids": False}}
    body = json.dumps(metadata).encode()
    video = Path(video_path).read_bytes()
    start = b"--" + boundary.encode() + b"\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n" + body + b"\r\n--" + boundary.encode() + b"\r\nContent-Type: video/mp4\r\n\r\n" + video + b"\r\n--" + boundary.encode() + b"--\r\n"
    url = "https://www.googleapis.com/upload/youtube/v3/videos?part=snippet,status&uploadType=multipart"
    req = urllib.request.Request(url, data=start, headers={"Authorization": f"Bearer {token}", "Content-Type": f"multipart/related; boundary={boundary}"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as response:
        return json.loads(response.read().decode())["id"]
