from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..config import settings
from ..fsops import remove_tree
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

import json

@router.get("/api/workspaces/{id}/stats")
def workspace_stats(id: str, request: Request) -> dict:
    registry = request.app.state.registry
    entry = registry.get(id)
    if entry is None:
        raise HTTPException(status_code=404, detail="No such workspace")
        
    export_root = Path(entry.export_root)
    if not export_root.exists():
        return {"albumCount": 0, "mediaBytes": 0, "dateStart": None, "dateEnd": None}
        
    state_dir = settings.workspace_dir / "state" / id
    state_dir.mkdir(parents=True, exist_ok=True)
    stats_file = state_dir / "stats_cache.json"
    
    if stats_file.exists():
        try:
            import json
            with open(stats_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
            
    from archivenetwork.inventory.parser import build_inventory
    try:
        inv = build_inventory(export_root)
    except Exception:
        return {"albumCount": 0, "mediaBytes": 0, "dateStart": None, "dateEnd": None}
    
    total_albums = len(inv.albums) + len(inv.archived_albums)
    size = sum(p.file_size_bytes for p in inv.all_photos())
    
    timestamps = []
    for p in inv.all_photos():
        ts = p.taken_timestamp or p.post_timestamp or p.creation_at
        if ts:
            timestamps.append(ts.timestamp())
            
    stats = {
        "albumCount": total_albums,
        "mediaBytes": size,
        "dateStart": min(timestamps) if timestamps else None,
        "dateEnd": max(timestamps) if timestamps else None,
    }
    
    try:
        import json
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f)
    except Exception:
        pass
        
    return stats


@router.post("/api/workspaces/open")
def open_workspace(request: Request, body: OpenRequest) -> dict:
    registry = request.app.state.registry
    entry = registry.get(body.id)
    if entry is None:
        raise HTTPException(status_code=404, detail="No such workspace")
    root = Path(entry.export_root)
    if not root.exists():
        raise HTTPException(status_code=410, detail="Workspace files are missing")
    # Reopen under the stored id (which may be zip-derived, not the folder name) so
    # the registry entry and its state dir stay stable across sessions.
    return _start_session(request, root, managed=entry.managed, source_name=entry.id)


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
        ok_state = remove_tree(state_dir)
        ok_import = True
        if imports_base in root.parents:
            import_child = root
            while import_child.parent != imports_base:
                import_child = import_child.parent
            ok_import = remove_tree(import_child)
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
