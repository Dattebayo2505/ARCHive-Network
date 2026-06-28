from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from ..config import settings
from ..ingest.unzip import extract_zip
from ..ingest.validate import find_export_root, validate_export
from ..inventory.parser import build_inventory
from ..selection.policy import DefaultPolicy
from ..selection.state import SelectionState
from ..thumbnails.service import ThumbnailService
from .session import Session

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return request.app.state.templates.TemplateResponse(request, "index.html", {"errors": None})


def _start_session(request: Request, export_root: Path):
    report = validate_export(export_root)
    if not report.ok:
        return request.app.state.templates.TemplateResponse(
            request, "index.html", {"errors": report.missing}, status_code=200
        )
    workspace = settings.workspace_dir
    session = Session(
        export_root=export_root,
        inventory=build_inventory(export_root),
        selection=SelectionState(workspace / "selection.json", DefaultPolicy()),
        thumbnails=ThumbnailService(workspace / "thumbs"),
    )
    request.app.state.session = session
    return RedirectResponse("/gallery", status_code=303)


@router.post("/load-folder")
def load_folder(request: Request, folder: str = Form(...)):
    return _start_session(request, find_export_root(Path(folder)))


@router.post("/upload")
def upload(request: Request, file: UploadFile = File(...)):
    workspace = settings.workspace_dir
    import_dir = workspace / "import"
    import_dir.mkdir(parents=True, exist_ok=True)
    zip_path = import_dir / (file.filename or "export.zip")
    zip_path.write_bytes(file.file.read())
    extracted = extract_zip(zip_path, import_dir / "unzipped")
    return _start_session(request, find_export_root(extracted))
