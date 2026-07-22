from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from ..config import settings
from ..inventory.hashtags import join_hashtags, split_hashtags
from ..reveal import RevealError, reveal_path
from ..selection.autocurate import auto_curate
from ..selection.policy import CapExceeded, NotSelectable
from ..thumbnails.service import ThumbnailService
from .serializers import inventory_payload

router = APIRouter()


class ToggleRequest(BaseModel):
    album_fbid: str
    photo_fbid: str


class CurateRequest(BaseModel):
    per_album: int | None = None


class DeselectAllRequest(BaseModel):
    album_fbid: str


class RenameAlbumRequest(BaseModel):
    album_fbid: str
    name: str


class CaptionAlbumRequest(BaseModel):
    album_fbid: str
    # Prose only, no hashtags — the tags are re-attached server-side from the export's own
    # caption, so editing prose can never delete the canonical section tag.
    caption: str = ""


class ArchiveAlbumRequest(BaseModel):
    album_fbid: str


class IncreaseLimitRequest(BaseModel):
    album_fbid: str


class RevealRequest(BaseModel):
    photo_fbid: str | None = None
    album_fbid: str | None = None


def _session(request: Request):
    session = request.app.state.session
    if session is None:
        raise HTTPException(status_code=404, detail="No export loaded")
    return session


@router.get("/api/inventory")
def inventory(request: Request) -> dict:
    session = _session(request)
    return inventory_payload(
        session.export_root.name,
        session.inventory,
        session.selection,
        session.selection.policy.max_per_album,
        session.limits,
        video_thumbs=session.video_thumbs,
    )


@router.get("/api/thumb/{fbid}")
def thumb(request: Request, fbid: str):
    session = _session(request)
    photo = session.inventory.photo_by_fbid(fbid)
    if photo is None or not photo.exists:
        raise HTTPException(status_code=404, detail="No such photo")
        
    if photo.is_video:
        path = session.video_thumbs.path(fbid)
        if not path.exists():
            raise HTTPException(status_code=404, detail="No thumbnail for video")
    else:
        path = session.thumbnails.thumbnail_path(fbid, photo.resolved_path)
        
    resp = FileResponse(path, media_type="image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=3600, immutable"
    return resp


@router.get("/api/preview/{fbid}")
def preview(request: Request, fbid: str):
    """A larger cached thumbnail for the full-screen preview viewer.

    The 256px gallery thumbnails look soft blown up to fill the screen, so the
    viewer pulls a crisper render. Reuses the same on-disk cache (keyed by size)
    and reads the read-only original — nothing in the export is modified.
    """
    session = _session(request)
    photo = session.inventory.photo_by_fbid(fbid)
    if photo is None or not photo.exists:
        raise HTTPException(status_code=404, detail="No such photo")
        
    if photo.is_video:
        path = session.video_thumbs.path(fbid)
        if not path.exists():
            raise HTTPException(status_code=404, detail="No preview for video")
    else:
        previews = ThumbnailService(session.thumbnails.cache_dir, size=settings.preview_size)
        path = previews.thumbnail_path(fbid, photo.resolved_path)
        
    resp = FileResponse(path, media_type="image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=3600, immutable"
    return resp


def _reveal_target(session, body: RevealRequest) -> Path:
    """Resolve which on-disk path a reveal request points at.

    A photo reveals its own file; an album reveals the media folder its photos
    live in. The path is confined to the loaded export so a reveal can never
    point the file manager outside the read-only original.
    """
    if body.photo_fbid:
        photo = session.inventory.photo_by_fbid(body.photo_fbid)
        if photo is None or not photo.exists:
            raise HTTPException(status_code=404, detail="No such photo")
        target = photo.resolved_path
    elif body.album_fbid:
        album = next(
            (a for a in session.inventory.albums if a.fb_album_id == body.album_fbid),
            None,
        )
        if album is None or not album.photos:
            raise HTTPException(status_code=404, detail="No such album")
        target = album.photos[0].resolved_path.parent
    else:
        raise HTTPException(status_code=400, detail="photo_fbid or album_fbid required")

    root = session.export_root.resolve()
    resolved = target.resolve()
    if resolved != root and root not in resolved.parents:
        raise HTTPException(status_code=403, detail="Path is outside the export")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File is missing from the export")
    return resolved


@router.post("/api/reveal")
def reveal(request: Request, body: RevealRequest):
    """Open the host file manager on a photo's file or an album's folder."""
    session = _session(request)
    target = _reveal_target(session, body)
    try:
        reveal_path(target)
    except RevealError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/api/stats/seen")
def mark_stats_seen(request: Request) -> dict:
    """Persist that the workspace-stats popup was shown for this workspace."""
    session = _session(request)
    (session.state_dir / "stats_seen.json").write_text('{"seen": true}', encoding="utf-8")
    return {"ok": True}


@router.post("/api/toggle")
def toggle(request: Request, body: ToggleRequest):
    session = _session(request)
    try:
        selected = session.selection.toggle(body.album_fbid, body.photo_fbid)
    except NotSelectable:
        # Separate from "cap": this album can never ship, so there is no swap to offer.
        return JSONResponse(
            {
                "error": "disregarded",
                "detail": "Photos without an album cannot be part of the ready folder.",
                "count": session.selection.count(body.album_fbid),
            },
            status_code=409,
        )
    except CapExceeded:
        return JSONResponse(
            {"error": "cap", "count": session.selection.count(body.album_fbid)},
            status_code=409,
        )
    return {"selected": selected, "count": session.selection.count(body.album_fbid)}


@router.post("/api/deselect_all")
def deselect_all(request: Request, body: DeselectAllRequest):
    session = _session(request)
    session.selection.deselect_all(body.album_fbid)
    return {"ok": True, "count": 0}


@router.post("/api/curate")
def curate(request: Request, body: CurateRequest | None = None):
    """Auto-curate: pick ≤N photos per album and every video, replacing the selection.

    Lives here, not under `/api/dev/*`: this is a *selection* operation and has nothing to do
    with Postgres, so gating it on `database_url` (as every dev route is) would be wrong. The
    Dev panel is merely where the button lives.
    """
    session = _session(request)
    per_album = body.per_album if body and body.per_album else settings.max_per_album
    result = auto_curate(session.inventory, session.selection, per_album)
    return {
        "per_album": per_album,
        "photos_selected": result.photos_selected,
        "videos_selected": result.videos_selected,
        "albums": [
            {
                "fb_album_id": a.fb_album_id,
                "name": a.name,
                "picked": a.picked,
                "available": a.available,
            }
            for a in result.albums
        ],
    }


@router.post("/api/album/rename")
def rename_album(request: Request, body: RenameAlbumRequest):
    """Rename an album (display name only — the export on disk is untouched)."""
    session = _session(request)
    album = next(
        (a for a in session.inventory.albums if a.fb_album_id == body.album_fbid),
        None,
    )
    if album is None:
        raise HTTPException(status_code=404, detail="No such album")
    new_name = body.name.strip()
    if len(new_name) < 5:
        raise HTTPException(status_code=400, detail="Album name must be at least 5 characters long.")
        
    for a in session.inventory.albums:
        if a.fb_album_id != album.fb_album_id and a.name.lower() == new_name.lower():
            raise HTTPException(status_code=409, detail=f'An album named "{new_name}" already exists')
    album.name = new_name
    session.renames.set_name(album.fb_album_id, new_name)
    return {"ok": True, "name": new_name}


@router.post("/api/album/reset")
def reset_album(request: Request, body: RenameAlbumRequest):
    """Reset an album's name back to its original name."""
    session = _session(request)
    album = next(
        (a for a in session.inventory.albums if a.fb_album_id == body.album_fbid),
        None,
    )
    if album is None:
        raise HTTPException(status_code=404, detail="No such album")
    
    if album.original_name:
        album.name = album.original_name
    session.renames.remove_name(album.fb_album_id)
    return {"ok": True, "name": album.name}


MAX_CAPTION_LEN = 2000


def _find_album(session, album_fbid: str):
    album = next((a for a in session.inventory.albums if a.fb_album_id == album_fbid), None)
    if album is None:
        raise HTTPException(status_code=404, detail="No such album")
    return album


@router.post("/api/album/caption")
def set_album_caption(request: Request, body: CaptionAlbumRequest):
    """Override an album's caption (display + build only — the export on disk is untouched).

    The request carries **prose**; the album's original hashtags are re-attached here before
    the raw caption is stored, so `#ARCHNews` — which decides the album's storage key and its
    `hashtag` column downstream — survives every edit. Clearing the prose leaves a
    tags-only caption rather than dropping the tags.
    """
    session = _session(request)
    album = _find_album(session, body.album_fbid)

    prose = body.caption.strip()
    if len(prose) > MAX_CAPTION_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Caption must be {MAX_CAPTION_LEN} characters or fewer.",
        )

    _, tags = split_hashtags(album.original_description)
    raw = join_hashtags(prose, tags)
    if raw is None:
        # Nothing left to say and no tags to keep: that is a reset, not an empty override.
        session.captions.remove_caption(album.fb_album_id)
        album.description = album.original_description
        album.caption_edited = False
    else:
        session.captions.set_caption(album.fb_album_id, raw)
        album.description = raw
        album.caption_edited = True
    description, hashtags = split_hashtags(album.description)
    return {
        "ok": True,
        "description": description,
        "hashtags": hashtags,
        "caption_edited": album.caption_edited,
    }


@router.post("/api/album/caption/reset")
def reset_album_caption(request: Request, body: ArchiveAlbumRequest):
    """Drop the caption override and restore the caption the export shipped with."""
    session = _session(request)
    album = _find_album(session, body.album_fbid)
    session.captions.remove_caption(album.fb_album_id)
    album.description = album.original_description
    album.caption_edited = False
    description, hashtags = split_hashtags(album.description)
    return {"ok": True, "description": description, "hashtags": hashtags, "caption_edited": False}


@router.post("/api/album/increase_limit")
def increase_limit(request: Request, body: IncreaseLimitRequest):
    """Increase the image limit of an album, bypassing the 10 max up to 15."""
    session = _session(request)
    album = next(
        (a for a in session.inventory.albums if a.fb_album_id == body.album_fbid),
        None,
    )
    if album is None:
        raise HTTPException(status_code=404, detail="No such album")
    
    new_max = min(15, len(album.photos))
    session.limits.set_limit(album.fb_album_id, new_max)
    return {"ok": True, "max_per_album": new_max}


@router.post("/api/album/undo_increase_limit")
def undo_increase_limit(request: Request, body: IncreaseLimitRequest):
    """Revert the image limit of an album to default, removing overflow selected items."""
    session = _session(request)
    album = next(
        (a for a in session.inventory.albums if a.fb_album_id == body.album_fbid),
        None,
    )
    if album is None:
        raise HTTPException(status_code=404, detail="No such album")
    
    default_max = session.selection.policy.max_per_album
    session.limits.remove_limit(album.fb_album_id)
    deselected = session.selection.truncate_to(album.fb_album_id, default_max)
    return {"ok": True, "max_per_album": default_max, "count": session.selection.count(album.fb_album_id), "deselected": deselected}



@router.post("/api/album/archive")
def archive_album(request: Request, body: ArchiveAlbumRequest):
    """Move an album to the archive list."""
    session = _session(request)
    inv = session.inventory
    album = next(
        (a for a in inv.albums if a.fb_album_id == body.album_fbid),
        None,
    )
    if album is None:
        raise HTTPException(status_code=404, detail="No such album")
    
    # We no longer set photo.archived = True here, they just move with the album
    # to inv.archived_albums which is excluded from builder.
    
    inv.archived_albums.append(album)
    session.archive.add(body.album_fbid)

    # Clear any selections for this album.
    sel = session.selection._selected.pop(body.album_fbid, None)
    if sel is not None:
        session.selection._save()
    inv.albums = [a for a in inv.albums if a.fb_album_id != body.album_fbid]
    return {"ok": True, "moved": len(album.photos)}


@router.post("/api/album/unarchive")
def unarchive_album(request: Request, body: ArchiveAlbumRequest):
    """Restore an album from the archive list back to albums."""
    session = _session(request)
    inv = session.inventory
    album = next(
        (a for a in inv.archived_albums if a.fb_album_id == body.album_fbid),
        None,
    )
    if album is None:
        raise HTTPException(status_code=404, detail="No such archived album")
    
    inv.albums.append(album)
    inv.archived_albums = [a for a in inv.archived_albums if a.fb_album_id != body.album_fbid]
    session.archive.remove(body.album_fbid)

    return {"ok": True, "moved": len(album.photos)}
