from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from ..config import settings
from ..reveal import RevealError, reveal_path
from ..selection.policy import CapExceeded
from ..thumbnails.service import ThumbnailService
from .serializers import inventory_payload

router = APIRouter()


class ToggleRequest(BaseModel):
    album_fbid: str
    photo_fbid: str


class RenameAlbumRequest(BaseModel):
    album_fbid: str
    name: str


class ArchiveAlbumRequest(BaseModel):
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
    )


@router.get("/api/thumb/{fbid}")
def thumb(request: Request, fbid: str):
    session = _session(request)
    photo = session.inventory.photo_by_fbid(fbid)
    if photo is None or not photo.exists:
        raise HTTPException(status_code=404, detail="No such photo")
    path = session.thumbnails.thumbnail_path(fbid, photo.resolved_path)
    return FileResponse(path, media_type="image/jpeg")


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
    previews = ThumbnailService(session.thumbnails.cache_dir, size=settings.preview_size)
    path = previews.thumbnail_path(fbid, photo.resolved_path)
    return FileResponse(path, media_type="image/jpeg")


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


@router.post("/api/toggle")
def toggle(request: Request, body: ToggleRequest):
    session = _session(request)
    try:
        selected = session.selection.toggle(body.album_fbid, body.photo_fbid)
    except CapExceeded:
        return JSONResponse(
            {"error": "cap", "count": session.selection.count(body.album_fbid)},
            status_code=409,
        )
    return {"selected": selected, "count": session.selection.count(body.album_fbid)}


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


@router.post("/api/album/archive")
def archive_album(request: Request, body: ArchiveAlbumRequest):
    """Move every photo in an album to the archive, then remove the album."""
    session = _session(request)
    inv = session.inventory
    album = next(
        (a for a in inv.albums if a.fb_album_id == body.album_fbid),
        None,
    )
    if album is None:
        raise HTTPException(status_code=404, detail="No such album")
    moved = 0
    for photo in album.photos:
        photo.archived = True
        inv.archived_photos.append(photo)
        moved += 1
    # Clear any selections for this album.
    sel = session.selection._selected.pop(body.album_fbid, None)
    if sel is not None:
        session.selection._save()
    inv.albums = [a for a in inv.albums if a.fb_album_id != body.album_fbid]
    return {"ok": True, "moved": moved}
