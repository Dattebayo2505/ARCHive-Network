from __future__ import annotations

from .builder import BuildResult


def format_summary(result: BuildResult) -> str:
    lines = [
        f"Ready folder: {result.ready_root}",
        f"Media files copied: {result.copied}",
        f"Albums written: {result.albums_written}",
        f"Orphans (referenced but missing on disk): {len(result.orphans)}",
    ]
    lines.extend(f"  - {o}" for o in result.orphans)
    return "\n".join(lines)
