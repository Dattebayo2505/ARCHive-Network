"""Orchestrate the ETL into DynamoDB: resolve files -> pre-fetch -> store the bytes -> UpdateItem.

The object store is written **before** the item, so an item can never point at an object that
does not exist. That is also why the `BatchGetItem` pre-fetch comes first: the storage key is
**frozen after first insert**, so a re-load must know the key already recorded on the item before
it uploads anything, or it could re-key a photo and strand or duplicate its object.

Every write is one `UpdateItem` (`dynamo.upsert`), never a `PutItem`. There is no load-wide
transaction: each item is atomic and a re-run converges. A CMS tombstone (`deleted_at`) wins:
the item is skipped, its bytes are not re-uploaded, and its key is reported in `skipped_deleted`.
boto errors propagate; the route maps them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import dynamo
from .items import album_pk, album_update, media_pk, media_update
from .read import MediaRow, read_ready
from .storage import Storage


@dataclass
class LoadResult:
    albums_inserted: int = 0
    albums_updated: int = 0
    media_inserted: int = 0
    media_updated: int = 0
    files_stored: int = 0
    files_skipped: int = 0
    orphans: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Item keys (`MEDIA#g01`) the CMS tombstoned; len() is the spec's skipped_deleted count.
    skipped_deleted: list[str] = field(default_factory=list)


def load(
    ready_root: Path,
    workspace_id: str,
    storage: Storage,
    table: dynamo.Table,
    *,
    now: datetime | None = None,
) -> LoadResult:
    now = now or datetime.now(UTC).replace(microsecond=0)  # one stamp for the whole run
    data = read_ready(ready_root)
    result = LoadResult()

    # 1. Resolve every uri to a real file. A uri with no file is an orphan: reported, never loaded.
    resolved: list[tuple[MediaRow, Path]] = []
    for row in data.media:
        src = ready_root / row.uri
        if not src.exists():
            result.orphans.append(row.uri)
            continue
        resolved.append((row, src))

    # 2. Pre-fetch what already exists: the frozen keys, the tombstones, and insert-vs-update.
    existing = dynamo.prefetch(
        table,
        [album_pk(a.fb_album_id) for a in data.albums]
        + [media_pk(row.fbid) for row, _ in resolved],
    )

    # 3. Store the bytes (idempotent), reusing the frozen key where one exists.
    keyed: list[tuple[MediaRow, str]] = []
    for row, src in resolved:
        pk = media_pk(row.fbid)
        prior = existing.get(pk)
        if prior and prior.deleted:
            result.skipped_deleted.append(pk)
            continue
        key = (prior and prior.storage_path) or storage.key_for(
            row.fbid, row.hashtag, row.group, src.suffix
        )
        try:
            if storage.put(src, key):
                result.files_stored += 1
            else:
                result.files_skipped += 1
        except OSError as exc:  # a single unreadable file must not sink the run
            result.errors.append(f"{row.fbid}: {exc}")
            continue
        keyed.append((row, key))

    # 4. Albums, then 5. media. The condition in `upsert` still guards a tombstone that landed
    # after the pre-fetch.
    for album in data.albums:
        pk = album_pk(album.fb_album_id)
        prior = existing.get(pk)
        if prior and prior.deleted:
            result.skipped_deleted.append(pk)
            continue
        if dynamo.upsert(table, album_update(album, now)) == "skipped_deleted":
            result.skipped_deleted.append(pk)
        elif pk in existing:
            result.albums_updated += 1
        else:
            result.albums_inserted += 1

    for row, key in keyed:
        pk = media_pk(row.fbid)
        if dynamo.upsert(table, media_update(row, key, workspace_id, now)) == "skipped_deleted":
            result.skipped_deleted.append(pk)
        elif pk in existing:
            result.media_updated += 1
        else:
            result.media_inserted += 1

    return result
