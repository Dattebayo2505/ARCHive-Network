from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from ..config import settings
from ..ingest.browse import list_directory
from ..ingest.unzip import extract_zip
from ..ingest.validate import find_export_root, validate_export
from ..inventory.parser import build_inventory
from ..selection.policy import DefaultPolicy
from ..selection.state import SelectionState
from ..thumbnails.service import ThumbnailService
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
    return {"loaded": True, "export_name": session.export_root.name}


def _start_session(request: Request, export_root: Path) -> dict:
    report = validate_export(export_root)
    if not report.ok:
        return {"ok": False, "errors": list(report.missing)}
    workspace = settings.workspace_dir
    request.app.state.session = Session(
        export_root=export_root,
        inventory=build_inventory(export_root),
        selection=SelectionState(workspace / "selection.json", DefaultPolicy()),
        thumbnails=ThumbnailService(workspace / "thumbs"),
    )
    return {"ok": True, "errors": [], "export_name": export_root.name}


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
    return _start_session(request, find_export_root(Path(body.folder)))


@router.post("/api/ingest/zip")
def ingest_zip(request: Request, body: ZipRequest) -> dict:
    """Unzip a `.zip` already on this machine — no HTTP upload of the archive.

    The browser can't hand the server a file path's *contents* securely, but the
    server runs locally, so it can read the user-picked archive straight off
    disk and extract it. Far cheaper than re-uploading ~900 MB.
    """
    src = Path(body.path).expanduser()
    if not src.is_file() or src.suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Not a .zip file on this computer")
    extracted = settings.workspace_dir / "import" / "unzipped"
    try:
        extract_zip(src, extracted)
    except (zipfile.BadZipFile, ValueError, subprocess.CalledProcessError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not unzip that archive: {exc}") from exc
    return _start_session(request, find_export_root(extracted))


@router.post("/api/ingest/upload")
def ingest_upload(request: Request, file: UploadFile = File(...)) -> dict:
    workspace = settings.workspace_dir
    import_dir = workspace / "import"
    import_dir.mkdir(parents=True, exist_ok=True)
    zip_path = import_dir / (file.filename or "export.zip")
    # Stream the upload to disk in chunks rather than reading the whole (~900 MB)
    # archive into memory.
    with zip_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    extracted = extract_zip(zip_path, import_dir / "unzipped")
    return _start_session(request, find_export_root(extracted))
