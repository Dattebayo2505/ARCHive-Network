"""Scan ``workspace/ready/`` and summarise each built folder.

Reuses ``loader.read.read_ready`` for counts — the same reconstructor the downstream
ETL uses — so the numbers shown match what would actually load, and the "ready folder
stands alone" guarantee is not weakened (this never touches ``build_inventory`` or the
live ``Session``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..inventory.naming import display_name
from ..loader.read import read_ready


@dataclass
class ReadyBuild:
    id: str
    display_name: str
    built_ts: float
    size_bytes: int
    photos: int | None
    videos: int | None
    albums: int | None


def _tree_size(root: Path) -> int:
    """Sum of every file's size under ``root``. Defensive: a file that errors on
    ``stat`` (locked, vanished) is skipped rather than sinking the whole scan."""
    total = 0
    for p in root.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def scan_ready_builds(ready_root: Path) -> list[ReadyBuild]:
    if not ready_root.is_dir():
        return []
    builds: list[ReadyBuild] = []
    for child in sorted(ready_root.iterdir()):
        # A real build is a directory containing a ``posts/`` manifest folder;
        # stray files or empty dirs are ignored.
        if not child.is_dir() or not (child / "posts").is_dir():
            continue
        photos = videos = albums = None
        try:
            result = read_ready(child)
            albums = len(result.albums)
            photos = sum(1 for m in result.media if m.media_type == "photo")
            videos = sum(1 for m in result.media if m.media_type == "video")
        except Exception:
            # A malformed build is still listed (with null counts) so the user can
            # see and reveal it; it must never break the whole listing.
            pass
        builds.append(
            ReadyBuild(
                id=child.name,
                display_name=display_name(child.name),
                built_ts=child.stat().st_mtime,
                size_bytes=_tree_size(child),
                photos=photos,
                videos=videos,
                albums=albums,
            )
        )
    builds.sort(key=lambda b: b.built_ts, reverse=True)
    return builds
