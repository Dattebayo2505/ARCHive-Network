"""Assertions about what actually landed in the database and the object store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import psycopg

from .read import read_ready
from .storage import Storage


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def validate(ready_root: Path, storage: Storage, conn: psycopg.Connection) -> list[Check]:
    data = read_ready(ready_root)
    checks: list[Check] = []

    with conn.cursor() as cur:
        cur.execute("SELECT fbid, storage_path, creation_at FROM media")
        rows = cur.fetchall()

    # Every row's object is really in the store.
    missing = [fbid for fbid, key, _ in rows if not storage.exists(key)]
    checks.append(
        Check(
            "every media.storage_path resolves in the store",
            not missing,
            f"{len(missing)} missing, e.g. {missing[:3]}",
        )
    )

    # Referential integrity (the FK enforces it; report it so a human can see that it held).
    with conn.cursor() as cur:
        cur.execute(
            """SELECT count(*) FROM media m
               LEFT JOIN photo_album a ON m.fb_album_id = a.fb_album_id
               WHERE m.fb_album_id IS NOT NULL AND a.fb_album_id IS NULL"""
        )
        dangling = cur.fetchone()[0]
    checks.append(Check("media.fb_album_id FK integrity", dangling == 0, f"{dangling} dangling"))

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) - count(DISTINCT fbid) FROM media")
        dupes = cur.fetchone()[0]
    checks.append(Check("media.fbid is unique", dupes == 0, f"{dupes} duplicates"))

    no_ts = [fbid for fbid, _, created in rows if created is None]
    checks.append(
        Check(
            "every media has a creation_at",
            not no_ts,
            f"{len(no_ts)} NULL, e.g. {no_ts[:3]}",
        )
    )

    # The DB agrees with the manifests about which media exist.
    expected = {m.fbid for m in data.media if (ready_root / m.uri).exists()}
    actual = {fbid for fbid, _, _ in rows}
    checks.append(
        Check(
            "row count reconciles with the ready manifests",
            expected == actual,
            f"manifests={len(expected)} db={len(actual)} "
            f"missing={sorted(expected - actual)[:3]} extra={sorted(actual - expected)[:3]}",
        )
    )

    # The ready folder holds no file the manifests forgot to mention. A manifest-driven ETL
    # cannot see such a file, so it would be silently dropped — the `n01` class of bug.
    media_dir = ready_root / "posts" / "media"
    on_disk = {
        str(p.relative_to(ready_root)).replace("\\", "/")
        for p in media_dir.rglob("*")
        if p.is_file()
    }
    unreferenced = sorted(on_disk - {m.uri for m in data.media})
    checks.append(
        Check(
            "every file in ready/ is referenced by a manifest",
            not unreferenced,
            f"{len(unreferenced)} unreferenced, e.g. {unreferenced[:3]}",
        )
    )

    return checks
