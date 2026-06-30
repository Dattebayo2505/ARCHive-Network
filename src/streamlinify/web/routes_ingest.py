from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile
from pydantic import BaseModel

from ..config import settings
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


@router.post("/api/ingest/folder")
def ingest_folder(request: Request, body: FolderRequest) -> dict:
    return _start_session(request, find_export_root(Path(body.folder)))


@router.post("/api/ingest/upload")
def ingest_upload(request: Request, file: UploadFile = File(...)) -> dict:
    workspace = settings.workspace_dir
    import_dir = workspace / "import"
    import_dir.mkdir(parents=True, exist_ok=True)
    zip_path = import_dir / (file.filename or "export.zip")
    zip_path.write_bytes(file.file.read())
    extracted = extract_zip(zip_path, import_dir / "unzipped")
    return _start_session(request, find_export_root(extracted))
