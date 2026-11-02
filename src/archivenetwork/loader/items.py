"""The ownership contract as code: read rows -> `Update` values (Official-Schema §3.1-3.2, §5.2).

Pure on purpose. `dynamo.upsert` turns an `Update` into one `UpdateItem`; this module decides
*what* the loader may write. It is the single home of the L / L1 attribute lists, so a review of
"which attributes does the loader own?" reads one file. Anything not named here is the CMS's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..inventory.hashtags import canonical_tag
from .read import AlbumRow, MediaRow


@dataclass(frozen=True)
class Update:
    """One item's write. `refresh` = L and S values (`None` means REMOVE); `set_once` = L1."""

    pk: str
    refresh: dict[str, Any]
    set_once: dict[str, Any]


# L (and S index keys): overwritten every load, REMOVEd when the export has no value.
ALBUM_REFRESH = frozenset({"title", "description", "date", "hashtags", "loaded_at"})
# L1: written once through if_not_exists; identity and history that never change.
ALBUM_SET_ONCE = frozenset({"id", "kind", "source", "created_at"})
MEDIA_REFRESH = frozenset(
    {
        "album_id",
        "media_type",
        "title",
        "description",
        "original_fb_uri",
        "creation_at",
        "hashtags",
        "source_workspace_id",
        "loaded_at",
        "GSI1PK",
        "GSI1SK",
    }
)
MEDIA_SET_ONCE = frozenset({"id", "storage_path", "fbid", "created_at"})

# C-owned: the loader never writes these. `deleted_at` is only read (pre-fetch) and named in the
# condition expression.
CMS_OWNED = frozenset(
    {
        "overrides",
        "updated_at",
        "updated_by",
        "deleted_at",
        "is_featured",
        "category_id",
        "department_id",
        "art_type",
        "project_title",
        "external",
        "GSI2PK",
        "GSI3PK",
        "GSI3SK",
    }
)
# Postgres-era / pre-ruling names the loader must never write again.
RETIRED = frozenset({"caption", "section_tag", "is_derived", "sort_order", "featured_rank"})

SK_META = "#META"


def album_pk(album_id: str) -> str:
    return f"ALBUM#{album_id}"


def media_pk(fbid: str) -> str:
    return f"MEDIA#{fbid}"


def _utc(dt: datetime) -> datetime:
    # A naive datetime is taken as UTC, never as the machine's local time.
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def iso_utc(dt: datetime) -> str:
    """`YYYY-MM-DDTHH:MM:SSZ`: fixed width, so it sorts as text inside GSI1SK."""
    return _utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_date(dt: datetime) -> str:
    """`YYYY-MM-DD`, the UTC calendar day."""
    return _utc(dt).strftime("%Y-%m-%d")


def album_update(row: AlbumRow, now: datetime) -> Update:
    stamp = iso_utc(now)
    return Update(
        pk=album_pk(row.fb_album_id),
        refresh={
            "title": row.title or None,
            "description": row.caption,
            "date": iso_date(row.date) if row.date else None,
            "hashtags": list(row.hashtags) or None,
            "loaded_at": stamp,
        },
        set_once={
            "id": row.fb_album_id,
            "kind": "photo",
            "source": "fb_export_derived" if row.is_derived else "fb_export",
            "created_at": stamp,
        },
    )


def media_update(row: MediaRow, storage_path: str, workspace_id: str, now: datetime) -> Update:
    stamp = iso_utc(now)
    loose = row.fb_album_id is None
    creation = iso_utc(row.creation_at) if row.creation_at else None
    # Anchored media read the album's text and tags, so theirs are REMOVEd (Official-Schema §3.2).
    if loose:
        partition = f"LOOSE#{canonical_tag(row.hashtags) or 'uncategorized'}"
    else:
        partition = album_pk(row.fb_album_id)
    return Update(
        pk=media_pk(row.fbid),
        refresh={
            "album_id": row.fb_album_id,
            "media_type": row.media_type,
            "title": row.title or None,
            "description": row.caption if loose else None,
            "original_fb_uri": row.uri,
            "creation_at": creation,
            "hashtags": (list(row.hashtags) or None) if loose else None,
            "source_workspace_id": workspace_id,
            "loaded_at": stamp,
            "GSI1PK": partition,
            "GSI1SK": creation,
        },
        set_once={
            "id": row.fbid,
            "storage_path": storage_path,
            "fbid": row.fbid,
            "created_at": stamp,
        },
    )
