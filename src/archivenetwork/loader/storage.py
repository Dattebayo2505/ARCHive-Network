from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Protocol


def media_key(fbid: str, creation_at: datetime | None, suffix: str) -> str:
    """The object-store key for one media file.

    Partitioned by the **post date** and named by the **fbid**. Both are properties of the
    content, not of the export run, so two overlapping weekly exports carrying the same photo
    compute the same key and merge instead of duplicating. (A workspace prefix would duplicate
    the object; an album prefix is unstable, because a derived caption-album's id is the first
    photo's fbid in the group and can shift when a later export joins that group.)
    """
    if creation_at is None:
        return f"media/unknown/{fbid}{suffix}"
    return f"media/{creation_at:%Y/%m/%d}/{fbid}{suffix}"


class Storage(Protocol):
    """The object store.

    `LocalStorage` for dev; an `S3Storage` drops in unchanged later — both compute the *same*
    key, so only the base URL used to render it differs. The DB stores the key, never the domain.
    """

    def key_for(self, fbid: str, creation_at: datetime | None, suffix: str) -> str: ...
    def exists(self, key: str) -> bool: ...
    def put(self, src: Path, key: str) -> bool: ...


class LocalStorage:
    """Dev backend: mirror the object store on disk under `root`, served over HTTP at /media."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def key_for(self, fbid: str, creation_at: datetime | None, suffix: str) -> str:
        return media_key(fbid, creation_at, suffix)

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
