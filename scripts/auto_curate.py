"""Headless curation: randomly pick <=N photos per album, then build the filtered ready
folder. Mirrors the web UI's selection + build, but non-interactive.

Nothing is auto-kept — exactly as in the UI, only picked photos ship. The synthetic
`__non_album__` bucket is just another album here, so its photos get the same random
<=N treatment. Videos are skipped: building one needs a client-captured still, which a
headless script cannot produce.

Usage:
    uv run python scripts/auto_curate.py <export-path> [--per-album 10] [--seed 0]

Output lands in workspace/ready/<export-name>/ (gitignored). Original export is read-only.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

# Allow running without an editable install (src layout).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from archivenetwork.config import settings  # noqa: E402
from archivenetwork.ingest.validate import find_export_root, validate_export  # noqa: E402
from archivenetwork.inventory.parser import build_inventory  # noqa: E402
from archivenetwork.transform.builder import build_ready_folder  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("export", type=Path, help="path to the FB export folder")
    ap.add_argument("--per-album", type=int, default=settings.max_per_album)
    ap.add_argument("--seed", type=int, default=None, help="RNG seed for reproducible picks")
    ap.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="output base (default: <workspace>/ready)",
    )
    args = ap.parse_args()

    rng = random.Random(args.seed)

    root = find_export_root(args.export)
    report = validate_export(root)
    if not report.ok:
        print(f"INVALID export at {root}: missing {report.missing}", file=sys.stderr)
        return 1
    print(f"Export root: {root}")

    inv = build_inventory(root)

    # Randomly select <= per-album existing photos per album. `__non_album__` is one of
    # these albums, so its photos are picked the same way — never auto-kept.
    keep: set[str] = set()
    print(f"\nAlbums ({len(inv.albums)}):")
    for album in inv.albums:
        usable = [p for p in album.photos if p.exists]
        n = min(args.per_album, len(usable))
        picked = rng.sample(usable, n) if n else []
        keep.update(p.fbid for p in picked)
        missing = len(album.photos) - len(usable)
        note = f"  ({missing} orphan refs skipped)" if missing else ""
        print(f"  - {album.name!r} [{album.fb_album_id}]: "
              f"kept {len(picked)} of {len(album.photos)}{note}")

    if inv.videos:
        print(f"\nVideos skipped: {len(inv.videos)} (a build needs a captured still — use the UI)")

    dest_base = args.dest or (settings.workspace_dir / "ready")
    dest = dest_base / root.name
    result = build_ready_folder(root, dest, keep)

    print("\n=== BUILD RESULT ===")
    print(f"ready_root     : {result.ready_root}")
    print(f"media copied   : {result.copied}")
    print(f"albums written : {result.albums_written}")
    print(f"orphans        : {len(result.orphans)}")
    if result.orphans:
        for o in result.orphans[:10]:
            print(f"  orphan: {o}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
