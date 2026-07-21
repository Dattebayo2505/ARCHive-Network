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


def summarise_build(path: Path) -> ReadyBuild | None:
    """Summarise one ``ready/<id>/`` folder, or ``None`` if it isn't a real build.

    A real build is a directory containing a ``posts/`` manifest folder; stray files,
    empty dirs and missing paths all read as "no build here".
    """
    if not path.is_dir() or not (path / "posts").is_dir():
        return None
    photos = videos = albums = None
    try:
        result = read_ready(path)
        albums = len(result.albums)
        photos = sum(1 for m in result.media if m.media_type == "photo")
        videos = sum(1 for m in result.media if m.media_type == "video")
    except Exception:
        # A malformed build is still reported (with null counts) so the user can see
        # and reveal it; it must never break the caller.
        pass
    return ReadyBuild(
        id=path.name,
        display_name=display_name(path.name),
        built_ts=path.stat().st_mtime,
        size_bytes=_tree_size(path),
        photos=photos,
        videos=videos,
        albums=albums,
    )


def scan_ready_builds(ready_root: Path) -> list[ReadyBuild]:
    if not ready_root.is_dir():
        return []
    builds = [b for child in sorted(ready_root.iterdir()) if (b := summarise_build(child))]
    builds.sort(key=lambda b: b.built_ts, reverse=True)
    return builds
