"""Orchestrate the ETL into DynamoDB: resolve files -> pre-fetch -> store the bytes -> UpdateItem.

The object store is written **before** the item, so an item can never point at an object that
does not exist. That is also why the `BatchGetItem` pre-fetch comes first: the storage key is
**frozen after first insert**, so a re-load must know the key already recorded on the item before
it uploads anything, or it could re-key a photo and strand or duplicate its object.

Every write is one `UpdateItem` (`dynamo.upsert`), never a `PutItem`. There is no load-wide
transaction: each item is atomic and a re-run converges. A CMS tombstone (`deleted_at`) wins:
the item is skipped, its bytes are not re-uploaded, and it is reported in `skipped_deleted` as
`album:<id>` / `media:<id>`. Items are keyed `(kind, id)` throughout: a derived album shares its
first photo's fbid, so an id alone is ambiguous across the album and media tables.
A per-file storage failure (`ClientError`, `BotoCoreError`, `OSError`) is recorded in `errors` and
`failed`, and that media item is **not** written, so no item names an object that is not there. A
credential error (`CREDENTIAL_ERRORS`) is a whole-run blocker and re-raises: every later file would
fail the same way. DynamoDB errors propagate; the route maps them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from . import dynamo
from .items import album_update, media_update
from .read import MediaRow, read_ready
from .storage import Storage

# Error codes meaning "this identity can't write here at all", not "this one file failed".
CREDENTIAL_ERRORS: frozenset[str] = frozenset({
    "ExpiredToken",
    "ExpiredTokenException",
    "InvalidClientTokenId",
    "UnrecognizedClientException",
    "InvalidAccessKeyId",
    "SignatureDoesNotMatch",
    "AccessDenied",
})


# A HEAD response has no body, so S3 reports an expired token (400) or a denial (403) as a bare
# status code. `put()` HEADs before it writes, so these are whole-run blockers too.
HEAD_CREDENTIAL_STATUSES: frozenset[str] = frozenset({"400", "403"})


def is_credential_error(exc: BaseException) -> bool:
    code = error_code(exc)
    return code in CREDENTIAL_ERRORS or code in HEAD_CREDENTIAL_STATUSES


def error_code(exc: BaseException) -> str:
    if isinstance(exc, ClientError):
        return str(exc.response.get("Error", {}).get("Code", ""))
    return ""


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
    # `kind:id` (`media:g01`) of each item the CMS tombstoned; len() is the skipped_deleted count.
    skipped_deleted: list[str] = field(default_factory=list)
    # fbids whose bytes failed to store; their items were not written.
    failed: list[str] = field(default_factory=list)


def load(
    ready_root: Path,
    workspace_id: str,
    storage: Storage,
    tables: dynamo.Tables,
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
        tables,
        [("album", a.fb_album_id) for a in data.albums]
        + [("media", row.fbid) for row, _ in resolved],
    )

    # 3. Store the bytes (idempotent), reusing the frozen key where one exists.
    keyed: list[tuple[MediaRow, str]] = []
    for row, src in resolved:
        ref = ("media", row.fbid)
        prior = existing.get(ref)
        if prior and prior.deleted:
            result.skipped_deleted.append(":".join(ref))
            continue
        key = (prior and prior.storage_path) or storage.key_for(
            row.fbid, row.hashtag, row.group, src.suffix
        )
        try:
            if storage.put(src, key):
                result.files_stored += 1
            else:
                result.files_skipped += 1
        except (ClientError, BotoCoreError, OSError) as exc:
            if is_credential_error(exc):
                raise
            # One bad file must not sink the run, and its item must not name a missing object.
            result.errors.append(f"{row.fbid}: {exc}")
            result.failed.append(row.fbid)
            continue
        keyed.append((row, key))

    # 4. Albums, then 5. media. The condition in `upsert` still guards a tombstone that landed
    # after the pre-fetch.
    for album in data.albums:
        ref = ("album", album.fb_album_id)
        prior = existing.get(ref)
        if prior and prior.deleted:
            result.skipped_deleted.append(":".join(ref))
            continue
        if dynamo.upsert(tables, album_update(album, now)) == "skipped_deleted":
            result.skipped_deleted.append(":".join(ref))
        elif ref in existing:
            result.albums_updated += 1
        else:
            result.albums_inserted += 1

    for row, key in keyed:
        ref = ("media", row.fbid)
        if dynamo.upsert(tables, media_update(row, key, workspace_id, now)) == "skipped_deleted":
            result.skipped_deleted.append(":".join(ref))
        elif ref in existing:
            result.media_updated += 1
        else:
            result.media_inserted += 1

    return result
