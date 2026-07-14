from __future__ import annotations

from ..inventory.hashtags import split_hashtags
from ..inventory.models import Album, ExportInventory, Photo
from ..selection.state import SelectionState
from ..inventory.limits import LimitState
from ..thumbnails.video_store import VideoThumbnailStore


def _photo(p: Photo, selected: bool | None = None) -> dict:
    # Hashtags leave the backend as structured data, never inline in prose: the caption is
    # clean everywhere it renders (tiles, preview, alt/title) and the UI parses nothing.
    caption, hashtags = split_hashtags(p.caption)
    d: dict = {
        "fbid": p.fbid,
        "caption": caption,
        "hashtags": hashtags,
        "exists": p.exists,
        "creation_at": p.creation_at.isoformat() if p.creation_at else None,
        "post_timestamp": p.post_timestamp.isoformat() if p.post_timestamp else None,
        "taken_timestamp": p.taken_timestamp.isoformat() if p.taken_timestamp else None,
        "file_size_bytes": p.file_size_bytes,
    }
    if selected is not None:
        d["selected"] = selected
    if getattr(p, "video_thumb_tag", None):
        d["video_thumb_tag"] = p.video_thumb_tag
    return d


def _archive_photo(p: Photo) -> dict:
    caption, hashtags = split_hashtags(p.caption)
    return {
        "fbid": p.fbid,
        "caption": caption,
        "hashtags": hashtags,
        "archive_tag": p.archive_tag,
        "exists": p.exists,
        "creation_at": p.creation_at.isoformat() if p.creation_at else None,
        "post_timestamp": p.post_timestamp.isoformat() if p.post_timestamp else None,
        "taken_timestamp": p.taken_timestamp.isoformat() if p.taken_timestamp else None,
        "file_size_bytes": p.file_size_bytes,
    }


def _album_cap(a: Album, max_per_album: int, limits: LimitState) -> int | None:
    """The album's selection cap, or **None when uncapped**.

    `None` is the wire contract for "no limit" — the UI renders "N selected · no limit" and
    never marks the album full. Uncapped albums (the derived caption-albums and the
    `__non_album__` bucket) short-circuit ahead of any `limits.json` override, exactly as
    `DefaultPolicy.can_select` does, so the two can never disagree.
    """
    if a.uncapped:
        return None
    return min(limits.get_limit(a.fb_album_id, max_per_album), len(a.photos))


def _album(a: Album, selection: SelectionState, max_per_album: int, limits: LimitState) -> dict:
    description, hashtags = split_hashtags(a.description)
    return {
        "fb_album_id": a.fb_album_id,
        "name": a.name,
        "original_name": a.original_name,
        "description": description,
        "hashtags": hashtags,
        "origin": a.origin,
        "post_timestamp": a.post_timestamp.isoformat() if a.post_timestamp else None,
        "count_selected": selection.count(a.fb_album_id),
        "max_per_album": _album_cap(a, max_per_album, limits),
        "limit_bypassed": limits.get_limit(a.fb_album_id, -1) != -1,
        "photos": [
            _photo(p, selected=selection.is_selected(a.fb_album_id, p.fbid)) for p in a.photos
        ],
    }


def inventory_payload(
    export_name: str,
    inventory: ExportInventory,
    selection: SelectionState,
    max_per_album: int,
    limits: LimitState,
    video_thumbs: VideoThumbnailStore | None = None,
) -> dict:
    return {
        "export_name": export_name,
        "max_per_album": max_per_album,
        "albums": [_album(a, selection, max_per_album, limits) for a in inventory.albums],
        "archived_albums": [
            _album(a, selection, max_per_album, limits) for a in inventory.archived_albums
        ],
        "non_album": [_photo(p) for p in inventory.non_album_photos],
        "videos": [
            {
                **_photo(v, selected=selection.is_selected("__videos__", v.fbid)),
                "video_thumb_tag": "AUTO" if video_thumbs and video_thumbs.is_auto(v.fbid) else "APPLIED" if video_thumbs and video_thumbs.has(v.fbid) else None,
                "file_size_bytes": video_thumbs.path(v.fbid).stat().st_size if video_thumbs and video_thumbs.has(v.fbid) else 0,
                "thumb_timestamp": video_thumbs.timestamp(v.fbid) if video_thumbs and video_thumbs.has(v.fbid) else None
            }
            for v in inventory.videos
        ],
        "archive": [_archive_photo(p) for p in inventory.archived_photos],
    }
