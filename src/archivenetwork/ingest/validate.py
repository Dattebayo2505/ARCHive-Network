from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REQUIRED = ["posts", "posts/album", "posts/media", "posts/profile_posts_1.json"]


@dataclass
class ValidationReport:
    ok: bool
    missing: list[str]
    root: Path


def validate_export(folder: Path) -> ValidationReport:
    missing = [rel for rel in REQUIRED if not (folder / rel).exists()]
    return ValidationReport(ok=not missing, missing=missing, root=folder)


def find_export_root(folder: Path) -> Path:
    """Return the folder that directly contains `posts/`, descending one level if needed."""
    if (folder / "posts").exists():
        return folder
    for child in sorted(p for p in folder.iterdir() if p.is_dir()):
        if (child / "posts").exists():
            return child
    return folder
