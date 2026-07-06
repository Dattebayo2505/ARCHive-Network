from __future__ import annotations

from ..inventory.models import ExportInventory, Photo
from ..selection.state import SelectionState


def _photo(p: Photo, selected: bool | None = None) -> dict:
    d: dict = {
        "fbid": p.fbid,
        "caption": p.caption,
        "exists": p.exists,
        "creation_at": p.creation_at.isoformat() if p.creation_at else None,
        "post_timestamp": p.post_timestamp.isoformat() if p.post_timestamp else None,
        "taken_timestamp": p.taken_timestamp.isoformat() if p.taken_timestamp else None,
        "file_size_bytes": p.file_size_bytes,
    }
    if selected is not None:
        d["selected"] = selected
    return d


def _archive_photo(p: Photo) -> dict:
    return {
        "fbid": p.fbid,
        "caption": p.caption,
        "archive_tag": p.archive_tag,
        "exists": p.exists,
        "creation_at": p.creation_at.isoformat() if p.creation_at else None,
        "post_timestamp": p.post_timestamp.isoformat() if p.post_timestamp else None,
        "taken_timestamp": p.taken_timestamp.isoformat() if p.taken_timestamp else None,
        "file_size_bytes": p.file_size_bytes,
    }


def inventory_payload(
    export_name: str,
    inventory: ExportInventory,
    selection: SelectionState,
    max_per_album: int,
) -> dict:
    albums = [
        {
            "fb_album_id": a.fb_album_id,
            "name": a.name,
            "original_name": a.original_name,
            "description": a.description,
            "origin": a.origin,
            "post_timestamp": a.post_timestamp.isoformat() if a.post_timestamp else None,
            "count_selected": selection.count(a.fb_album_id),
            "max_per_album": min(max_per_album, len(a.photos)),
            "photos": [
                _photo(p, selected=selection.is_selected(a.fb_album_id, p.fbid))
                for p in a.photos
            ],
        }
        for a in inventory.albums
    ]
    archived_albums = [
        {
            "fb_album_id": a.fb_album_id,
            "name": a.name,
            "original_name": a.original_name,
            "description": a.description,
            "origin": a.origin,
            "post_timestamp": a.post_timestamp.isoformat() if a.post_timestamp else None,
            "count_selected": selection.count(a.fb_album_id),
            "max_per_album": min(max_per_album, len(a.photos)),
            "photos": [
                _photo(p, selected=selection.is_selected(a.fb_album_id, p.fbid))
                for p in a.photos
            ],
        }
        for a in inventory.archived_albums
    ]
    return {
        "export_name": export_name,
        "max_per_album": max_per_album,
        "albums": albums,
        "archived_albums": archived_albums,
        "non_album": [_photo(p) for p in inventory.non_album_photos],
        "videos": [_photo(v) for v in inventory.videos],
        "archive": [_archive_photo(p) for p in inventory.archived_photos],
    }
