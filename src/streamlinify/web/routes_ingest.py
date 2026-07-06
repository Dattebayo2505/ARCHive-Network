from __future__ import annotations

import shutil
import subprocess
import time
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from ..config import settings
from ..ingest.browse import list_directory
from ..ingest.unzip import extract_zip
from ..ingest.validate import find_export_root, validate_export
from ..inventory.models import ExportInventory
from ..inventory.naming import display_name
from ..inventory.parser import build_inventory
from ..inventory.renames import RenameState
from ..selection.archive_state import ArchiveState
from ..selection.policy import DefaultPolicy
from ..selection.state import SelectionState
from ..thumbnails.service import ThumbnailService
from ..thumbnails.video_store import VideoThumbnailStore
from .session import Session

router = APIRouter()


class FolderRequest(BaseModel):
    folder: str


class ZipRequest(BaseModel):
    path: str


@router.get("/")
def health() -> dict:
    return {"name": "streamlinify", "status": "ok"}


@router.get("/api/session")
def session_status(request: Request) -> dict:
    session = request.app.state.session
    if session is None:
        return {"loaded": False, "export_name": None}
    return {
        "loaded": True,
        "export_name": session.export_root.name,
        "workspace_id": session.workspace_id,
        "display_name": display_name(session.workspace_id),
    }


def _apply_archive(inventory: ExportInventory, ids: set[str]) -> None:
    """Move albums whose fbid is in ``ids`` out of ``albums`` into ``archived_albums``.

    Restores the user's persisted album-archive decisions at session-build time,
    matching what ``POST /api/album/archive`` does at runtime. Order preserved.
    """
    if not ids:
        return
    to_archive = [a for a in inventory.albums if a.fb_album_id in ids]
    if not to_archive:
        return
    inventory.albums = [a for a in inventory.albums if a.fb_album_id not in ids]
    inventory.archived_albums.extend(to_archive)


def _maybe_adopt_legacy_state(state_dir: Path) -> None:
    """One-time: move pre-multi-workspace flat state into the first workspace.

    Before this feature, ``selection.json`` / ``renames.json`` lived directly in
    ``workspace/``. On the first workspace opened after upgrade, adopt them so the
    volunteer doesn't lose in-progress work. Guarded by a ``.migrated`` marker so
    it never runs twice; skipped if this workspace already has a state dir.
    """
    ws = settings.workspace_dir
    marker = ws / ".migrated"
    if marker.exists() or state_dir.exists():
        return
    state_dir.mkdir(parents=True, exist_ok=True)
    for name in ("selection.json", "renames.json"):
        legacy = ws / name
        if legacy.exists():
            shutil.move(str(legacy), str(state_dir / name))
    marker.write_text("1", encoding="utf-8")


def _start_session(
    request: Request, export_root: Path, *, managed: bool, source_name: str | None = None
) -> dict:
    report = validate_export(export_root)
    if not report.ok:
        return {"ok": False, "errors": list(report.missing)}

    registry = request.app.state.registry
    entry = registry.register(export_root, managed=managed, now=time.time(), ws_id=source_name)
    state_dir = settings.workspace_dir / "state" / entry.id
    _maybe_adopt_legacy_state(state_dir)

    inventory = build_inventory(export_root)
    renames = RenameState(state_dir / "renames.json")
    archive = ArchiveState(state_dir / "archive.json")
    for album in inventory.albums + inventory.archived_albums:
        album.original_name = album.name
        if album.fb_album_id in renames._renames:
            album.name = renames._renames[album.fb_album_id]
    _apply_archive(inventory, archive.archived_ids())

    request.app.state.session = Session(
        workspace_id=entry.id,
        state_dir=state_dir,
        export_root=export_root,
        inventory=inventory,
        selection=SelectionState(state_dir / "selection.json", DefaultPolicy()),
        thumbnails=ThumbnailService(state_dir / "thumbs"),
        video_thumbs=VideoThumbnailStore(state_dir / "thumbs" / "videos"),
        renames=renames,
        archive=archive,
    )
    return {
        "ok": True,
        "errors": [],
        "export_name": export_root.name,
        "workspace_id": entry.id,
        "display_name": entry.display_name,
    }


@router.get("/api/browse")
def browse(path: str | None = None) -> dict:
    """List sub-directories of `path` (defaults to home) for the folder picker."""
    try:
        return list_directory(Path(path) if path else None)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=400, detail=f"Cannot open folder: {exc}") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=f"Permission denied: {exc}") from exc


@router.post("/api/ingest/folder")
def ingest_folder(request: Request, body: FolderRequest) -> dict:
    return _start_session(request, find_export_root(Path(body.folder)), managed=False)


@router.post("/api/ingest/zip")
def ingest_zip(request: Request, body: ZipRequest) -> dict:
    """Unzip a `.zip` already on this machine into workspace/imports/<stem>/.

    Dedup: if that folder already exists we skip extraction and just open it.
    """
    src = Path(body.path).expanduser()
    if not src.is_file() or src.suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Not a .zip file on this computer")
    dest = settings.workspace_dir / "imports" / src.stem
    deduped = dest.exists()
    if not deduped:
        try:
            extract_zip(src, dest)
        except (zipfile.BadZipFile, ValueError, subprocess.CalledProcessError) as exc:
            raise HTTPException(status_code=400, detail=f"Could not unzip that archive: {exc}") from exc
    result = _start_session(request, find_export_root(dest), managed=True, source_name=src.stem)
    result["deduped"] = deduped
    return result


@router.post("/api/ingest/upload")
def ingest_upload(request: Request, file: UploadFile = File(...)) -> dict:
    workspace = settings.workspace_dir
    import_dir = workspace / "import"
    import_dir.mkdir(parents=True, exist_ok=True)
    zip_path = import_dir / (file.filename or "export.zip")
    dest = workspace / "imports" / Path(zip_path.name).stem
    try:
        with zip_path.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        if not dest.exists():
            extract_zip(zip_path, dest)
    finally:
        zip_path.unlink(missing_ok=True)
    return _start_session(
        request, find_export_root(dest), managed=True, source_name=Path(zip_path.name).stem
    )
