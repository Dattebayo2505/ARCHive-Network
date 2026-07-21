import os
from pathlib import Path

from archivenetwork.inventory.parser import build_inventory
from archivenetwork.transform.builder import build_ready_folder
from archivenetwork.transform.ready_index import scan_ready_builds


def _build(export_root: Path, dest: Path) -> None:
    inv = build_inventory(export_root)
    keep = {p.fbid for p in inv.all_photos() if not p.is_video}
    build_ready_folder(export_root, dest, keep)


def test_scan_lists_built_folder_with_counts(export_root: Path, tmp_path: Path):
    ready_root = tmp_path / "ready"
    _build(export_root, ready_root / "mybuild")
    builds = scan_ready_builds(ready_root)
    assert len(builds) == 1
    b = builds[0]
    assert b.id == "mybuild"
    assert b.size_bytes > 0
    assert b.albums is not None and b.albums >= 1
    assert b.photos is not None and b.photos >= 1


def test_scan_missing_dir_returns_empty(tmp_path: Path):
    assert scan_ready_builds(tmp_path / "nope") == []


def test_scan_skips_non_build_children(export_root: Path, tmp_path: Path):
    ready_root = tmp_path / "ready"
    _build(export_root, ready_root / "real")
    (ready_root / "stray_dir").mkdir()          # no posts/ -> not a build
    (ready_root / "loose.txt").write_text("x")  # a file -> not a build
    ids = [b.id for b in scan_ready_builds(ready_root)]
    assert ids == ["real"]


def test_scan_sorts_newest_first(export_root: Path, tmp_path: Path):
    ready_root = tmp_path / "ready"
    _build(export_root, ready_root / "older")
    _build(export_root, ready_root / "newer")
    os.utime(ready_root / "older", (1000, 1000))
    os.utime(ready_root / "newer", (2000, 2000))
    assert [b.id for b in scan_ready_builds(ready_root)] == ["newer", "older"]
