from __future__ import annotations

from .builder import BuildResult


def format_summary(result: BuildResult) -> str:
    lines = [
        f"Ready folder: {result.ready_root}",
        f"Media files copied: {result.copied}",
        f"Video stills written: {result.videos_built}",
        f"Albums written: {result.albums_written}",
        f"Orphans (referenced but missing on disk): {len(result.orphans)}",
    ]
    lines.extend(f"  - {o}" for o in result.orphans)
    if result.skipped_videos:
        lines.append(f"Videos skipped (no thumbnail chosen): {len(result.skipped_videos)}")
        lines.extend(f"  - {s}" for s in result.skipped_videos)
    return "\n".join(lines)
