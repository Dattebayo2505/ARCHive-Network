"""Orchestrate the ETL: resolve files -> store the bytes -> upsert the rows.

The object store is written **before** the database, so a row can never point at an object that
does not exist. The storage key is **frozen after first insert**: a re-load reuses the key already
recorded on the row, so it can never re-key a photo and thereby strand or duplicate an object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import psycopg

from .read import read_ready
from .storage import Storage

_UPSERT_ALBUM = """
INSERT INTO photo_album (fb_album_id, title, description, date, is_derived)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (fb_album_id) DO UPDATE SET
    title       = EXCLUDED.title,
    description = EXCLUDED.description,
    date        = EXCLUDED.date,
    is_derived  = EXCLUDED.is_derived
RETURNING (xmax = 0) AS inserted
"""

# `storage_path` is deliberately ABSENT from the UPDATE set — this is what enforces the key
# freeze at the SQL level. Do not add it.
_UPSERT_MEDIA = """
INSERT INTO media (fbid, media_type, fb_album_id, title, caption, description,
                   storage_path, original_fb_uri, creation_at, source_workspace_id)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (fbid) DO UPDATE SET
    media_type          = EXCLUDED.media_type,
    fb_album_id         = EXCLUDED.fb_album_id,
    title               = EXCLUDED.title,
    caption             = EXCLUDED.caption,
    description         = EXCLUDED.description,
    original_fb_uri     = EXCLUDED.original_fb_uri,
    creation_at         = EXCLUDED.creation_at,
    source_workspace_id = EXCLUDED.source_workspace_id,
    updated_at          = now()
RETURNING (xmax = 0) AS inserted
"""


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


def load(
    ready_root: Path, workspace_id: str, storage: Storage, conn: psycopg.Connection
) -> LoadResult:
    data = read_ready(ready_root)
    result = LoadResult()

    # 1. Resolve every uri to a real file. A uri with no file is an orphan: reported, never loaded.
    resolved: list[tuple] = []
    for row in data.media:
        src = ready_root / row.uri
        if not src.exists():
            result.orphans.append(row.uri)
            continue
        resolved.append((row, src))

    # 2. Fetch the keys of rows that already exist — this is the freeze.
    existing: dict[str, str] = {}
    fbids = [row.fbid for row, _ in resolved]
    if fbids:
        with conn.cursor() as cur:
            cur.execute("SELECT fbid, storage_path FROM media WHERE fbid = ANY(%s)", (fbids,))
            existing = dict(cur.fetchall())

    # 3. Store the bytes (idempotent), reusing the frozen key where one exists.
    keyed: list[tuple] = []
    for row, src in resolved:
        key = existing.get(row.fbid) or storage.key_for(row.fbid, row.creation_at, src.suffix)
        try:
            if storage.put(src, key):
                result.files_stored += 1
            else:
                result.files_skipped += 1
        except OSError as exc:  # a single unreadable file must not sink the run
            result.errors.append(f"{row.fbid}: {exc}")
            continue
        keyed.append((row, key))

    # 4. Albums first (the FK parent), then media.
    with conn.cursor() as cur:
        for album in data.albums:
            cur.execute(
                _UPSERT_ALBUM,
                (album.fb_album_id, album.title, album.description, album.date, album.is_derived),
            )
            if cur.fetchone()[0]:
                result.albums_inserted += 1
            else:
                result.albums_updated += 1

        for row, key in keyed:
            cur.execute(
                _UPSERT_MEDIA,
                (
                    row.fbid,
                    row.media_type,
                    row.fb_album_id,
                    row.title,
                    row.caption,
                    row.description,
                    key,
                    row.uri,
                    row.creation_at,
                    workspace_id,
                ),
            )
            if cur.fetchone()[0]:
                result.media_inserted += 1
            else:
                result.media_updated += 1
    conn.commit()
    return result
