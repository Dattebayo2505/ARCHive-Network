from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from ..selection.policy import CapExceeded
from .serializers import inventory_payload

router = APIRouter()


class ToggleRequest(BaseModel):
    album_fbid: str
    photo_fbid: str


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
