from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter()


def _session(request: Request):
    session = request.app.state.session
    if session is None:
        raise HTTPException(status_code=404, detail="No export loaded")
    return session


def _video(session, fbid: str):
    video = next((v for v in session.inventory.videos if v.fbid == fbid), None)
    if video is None:
        raise HTTPException(status_code=404, detail="No such video")
    return video


@router.get("/api/video/{fbid}")
def video_file(request: Request, fbid: str):
    """Stream the raw mp4 for in-browser playback. FileResponse honors Range
    requests, so the scrubber can seek. Read-only original; never modified."""
    session = _session(request)
    video = _video(session, fbid)
    if not video.resolved_path.exists():
        raise HTTPException(status_code=404, detail="Video file missing")
    return FileResponse(video.resolved_path, media_type="video/mp4")


@router.get("/api/video/{fbid}/thumbnail")
def get_video_thumbnail(request: Request, fbid: str):
    session = _session(request)
    _video(session, fbid)
    path = session.video_thumbs.path(fbid)
    if not path.exists():
        raise HTTPException(status_code=404, detail="No thumbnail chosen yet")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/api/video/{fbid}/thumbnail")
async def save_video_thumbnail(request: Request, fbid: str):
    """Store a frame captured client-side (raw JPEG bytes in the request body)."""
    session = _session(request)
    _video(session, fbid)
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Empty thumbnail body")
    session.video_thumbs.save(fbid, data)
    return {"ok": True}
