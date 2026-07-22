from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..config import settings
from ..fsops import remove_tree
from ..reveal import RevealError, reveal_path
from ..transform.ready_index import scan_ready_builds, summarise_build

router = APIRouter()


class RevealBuildRequest(BaseModel):
    id: str


class DeleteBuildRequest(BaseModel):
    id: str


def _ready_root():
    return settings.workspace_dir / "ready"


def _resolve_build(build_id: str):
    """Resolve ``id`` to an existing build folder, or 404.

    Path-safety: the target must be a *direct* child of ready_root that exists. A
    traversal id ("..") or an absolute path resolves elsewhere and is rejected — no
    route here may ever reveal, let alone delete, a folder outside workspace/ready/.
    """
    ready_root = _ready_root().resolve()
    target = (ready_root / build_id).resolve()
    if target.parent != ready_root or not target.is_dir():
        raise HTTPException(status_code=404, detail="No such build")
    return target


@router.get("/api/ready")
def list_ready(request: Request) -> dict:
    builds = scan_ready_builds(_ready_root())
    return {"builds": [asdict(b) for b in builds]}


@router.get("/api/ready/current")
def current_ready(request: Request) -> dict:
    """The ready build for the *loaded* workspace, or ``{"build": null}`` if it has
    never been built. Drives the gallery's "already built" indicator and the
    overwrite warning on the Build button — the build always writes to
    ``ready/<workspace_id>/``, so that one folder is the only one at risk."""
    session = request.app.state.session
    if session is None:
        raise HTTPException(status_code=404, detail="No export loaded")
    build = summarise_build(_ready_root() / session.workspace_id)
    return {"build": asdict(build) if build is not None else None}


@router.post("/api/ready/reveal")
def reveal_ready(body: RevealBuildRequest) -> dict:
    target = _resolve_build(body.id)
    try:
        reveal_path(target)
    except RevealError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/api/ready/delete")
def delete_ready(body: DeleteBuildRequest) -> dict:
    """Delete one built folder under workspace/ready/.

    Only the *output* is removed — the export, the workspace registry entry and the
    workspace's `state/<id>/` (selection, renames, captions) are all untouched, so
    the same picks rebuild the folder verbatim. That is what makes this safe to offer
    as a one-step destructive action: nothing curated is lost, only the copy on disk.
    """
    target = _resolve_build(body.id)
    if not remove_tree(target):
        raise HTTPException(
            status_code=500,
            detail="Could not delete the folder (it may be open in another program).",
        )
    return {"ok": True}
