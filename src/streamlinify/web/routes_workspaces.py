from __future__ import annotations

import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..config import settings
from .routes_ingest import _start_session

router = APIRouter()


class OpenRequest(BaseModel):
    id: str


class RemoveRequest(BaseModel):
    id: str
    delete_files: bool = False


@router.get("/api/workspaces")
def list_workspaces(request: Request) -> dict:
    registry = request.app.state.registry
    return {
        "workspaces": [
            {
                "id": e.id,
                "display_name": e.display_name,
                "raw_name": Path(e.export_root).name,
                "last_opened_ts": e.last_opened_ts,
                "managed": e.managed,
            }
            for e in registry.list()
        ],
        "last_active": registry.last_active,
    }


@router.post("/api/workspaces/open")
def open_workspace(request: Request, body: OpenRequest) -> dict:
    registry = request.app.state.registry
    entry = registry.get(body.id)
    if entry is None:
        raise HTTPException(status_code=404, detail="No such workspace")
    root = Path(entry.export_root)
    if not root.exists():
        raise HTTPException(status_code=410, detail="Workspace files are missing")
    return _start_session(request, root, managed=entry.managed)


def _remove_tree(path: Path, attempts: int = 5) -> bool:
    """Delete a directory tree, tolerating Windows file locks. Returns True iff gone."""
    for _ in range(attempts):
        if not path.exists():
            return True
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return True
        time.sleep(0.2)
    return not path.exists()


@router.post("/api/workspaces/remove")
def remove_workspace(request: Request, body: RemoveRequest) -> dict:
    registry = request.app.state.registry
    entry = registry.get(body.id)
    if entry is None:
        raise HTTPException(status_code=404, detail="No such workspace")

    deleted_files = False
    if body.delete_files and entry.managed:
        # Managed workspaces were unzipped under workspace/imports/<stem>/. Delete the
        # extraction folder (the direct child of imports/) plus the state dir. Guard so
        # we NEVER rmtree anything outside imports/, even if export_root is unexpected.
        root = Path(entry.export_root).resolve()
        imports_base = (settings.workspace_dir / "imports").resolve()
        state_dir = settings.workspace_dir / "state" / entry.id
        ok_state = _remove_tree(state_dir)
        ok_import = True
        if imports_base in root.parents:
            import_child = root
            while import_child.parent != imports_base:
                import_child = import_child.parent
            ok_import = _remove_tree(import_child)
        if not (ok_import and ok_state):
            raise HTTPException(
                status_code=500,
                detail="Could not delete all files (they may be open in another program). "
                "The workspace was kept in the list.",
            )
        deleted_files = True

    # Clear the live session if it was this workspace.
    session = request.app.state.session
    if session is not None and session.workspace_id == body.id:
        request.app.state.session = None

    registry.remove(body.id)
    return {"ok": True, "deleted_files": deleted_files}
