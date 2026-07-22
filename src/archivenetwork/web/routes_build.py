from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..reveal import RevealError, reveal_path
from ..transform.builder import build_ready_folder
from ..transform.report import format_summary

router = APIRouter()


@router.post("/api/build")
def build(request: Request) -> dict:
    session = request.app.state.session
    if session is None:
        raise HTTPException(status_code=404, detail="No export loaded")

    # Nothing is auto-kept: every photo, video and album in the build is one the user
    # explicitly picked. The selection is the single source of truth for what ships.
    keep = session.selection.selected_fbids()

    ready_root = settings.workspace_dir / "ready"
    # Name the ready folder from the workspace id (the friendly zip-based
    # ``facebook-<page>-<date>`` name), matching ``workspace/state/<id>/`` — not the generic
    # extracted-root name (``this_profile's_activity_across_facebook``). Falls back to the
    # export folder name for plain folder imports, where ``workspace_id == export_root.name``.
    dest = ready_root / session.workspace_id
    result = build_ready_folder(
        session.export_root,
        dest,
        keep,
        session.video_thumbs.dir,
        session.renames._renames,
        session.captions._captions,
    )

    # ARCHive Network owns the local desktop, so pop the OS file manager open on the
    # workspace/ready/ folder — the volunteer's next step is to grab the build. A
    # reveal failure must never sink an otherwise-successful build.
    try:
        reveal_path(ready_root)
    except RevealError:
        pass

    return {
        "copied": result.copied,
        "videos_built": result.videos_built,
        "skipped_videos": result.skipped_videos,
        "albums_written": result.albums_written,
        "orphans": result.orphans,
        "summary": format_summary(result),
    }
