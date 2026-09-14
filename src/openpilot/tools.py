from pathlib import Path


def list_files(workspace: str = ".", limit: int = 100) -> list[str]:
    root = Path(workspace).resolve()
    files: list[str] = []
    for path in root.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            files.append(str(path.relative_to(root)))
            if len(files) >= limit:
                break
    return sorted(files)


def read_text(path: str, max_chars: int = 10_000) -> str:
    return Path(path).read_text(encoding="utf-8")[:max_chars]
