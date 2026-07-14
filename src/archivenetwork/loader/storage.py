from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol

UNCATEGORIZED = "uncategorized"


def media_key(fbid: str, hashtag: str | None, group: str, suffix: str) -> str:
    """The object-store key for one media file.

    Grouped by the album's **canonical hashtag**, then by the album (or the literal
    `videos` / `unanchored` group), and named by the **fbid**:

        fb-exports/archevt/animusika-2026/1470662168409180.jpg

    The hashtag and the album name are mutable in principle, so this key is NOT
    self-healing the way the old date/fbid key was. What makes it safe is the freeze in
    `load.py`: `storage_path` is absent from the UPSERT's UPDATE set and `load()` reuses
    any key already on the row, so a renamed album yields a *stale-but-valid* key rather
    than a stranded object. Do not remove the freeze.

    Media with no canonical tag lands in `uncategorized/` — a deliberate, visible bucket,
    never a guess.
    """
    tag = (hashtag or UNCATEGORIZED).lower()
    return f"fb-exports/{tag}/{group}/{fbid}{suffix}"


class Storage(Protocol):
    """The object store.

    `LocalStorage` for dev; an `S3Storage` drops in unchanged later — both compute the *same*
    key, so only the base URL used to render it differs. The DB stores the key, never the domain.
    """

    def key_for(self, fbid: str, hashtag: str | None, group: str, suffix: str) -> str: ...
    def exists(self, key: str) -> bool: ...
    def put(self, src: Path, key: str) -> bool: ...


class LocalStorage:
    """Dev backend: mirror the object store on disk under `root`, served over HTTP at /store."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def key_for(self, fbid: str, hashtag: str | None, group: str, suffix: str) -> str:
        return media_key(fbid, hashtag, group, suffix)

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()

    def put(self, src: Path, key: str) -> bool:
        """Copy `src` to `key`. Returns False if the key already exists (idempotent)."""
        dst = self.root / key
        if dst.exists():
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
