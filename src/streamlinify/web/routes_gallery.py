from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from ..selection.policy import CapExceeded

router = APIRouter()


def _session(request: Request):
    session = request.app.state.session
    if session is None:
        raise HTTPException(status_code=404, detail="No export loaded")
    return session


@router.get("/gallery")
def gallery(request: Request):
    session = _session(request)
    return request.app.state.templates.TemplateResponse(
        request,
        "gallery.html",
        {
            "albums": session.inventory.albums,
            "non_album": session.inventory.non_album_photos,
            "selection": session.selection,
            "max_per_album": session.selection.policy.max_per_album,
        },
    )


@router.get("/thumb/{fbid}")
def thumb(request: Request, fbid: str):
    session = _session(request)
    photo = session.inventory.photo_by_fbid(fbid)
    if photo is None or not photo.exists:
        raise HTTPException(status_code=404, detail="No such photo")
    path = session.thumbnails.thumbnail_path(fbid, photo.resolved_path)
    return FileResponse(path, media_type="image/jpeg")


@router.post("/toggle")
def toggle(request: Request, album_fbid: str = Form(...), photo_fbid: str = Form(...)):
    session = _session(request)
    try:
        selected = session.selection.toggle(album_fbid, photo_fbid)
    except CapExceeded:
        return JSONResponse(
            {"error": "cap", "count": session.selection.count(album_fbid)}, status_code=409
        )
    return {"selected": selected, "count": session.selection.count(album_fbid)}
