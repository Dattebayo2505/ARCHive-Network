from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..transform.builder import build_ready_folder
from ..transform.report import format_summary

router = APIRouter()


@router.post("/build")
def build(request: Request):
    session = request.app.state.session
    if session is None:
        raise HTTPException(status_code=404, detail="No export loaded")

    keep = session.selection.selected_fbids()
    keep |= {p.fbid for p in session.inventory.non_album_photos if p.exists}

    dest = settings.workspace_dir / "ready" / session.export_root.name
    result = build_ready_folder(session.export_root, dest, keep)

    return request.app.state.templates.TemplateResponse(
        request, "summary.html", {"summary": format_summary(result), "result": result}
    )
