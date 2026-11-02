"""Dev-mode: run the real ETL against a DynamoDB table (floci locally) + a local object store.

Every route here 404s unless `settings.dynamodb_table` is set. The frontend toggle only
*reveals* the panel; the backend decides whether dev-mode is usable.

Handlers call `_table()` in their bodies, never through `Depends`: tests monkeypatch the module
attribute, and a `Depends` reference would silently bypass the patch.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Literal

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ..config import settings
from ..loader import dynamo
from ..loader.load import load
from ..loader.storage import LocalStorage
from ..loader.validate import validate

router = APIRouter()

_BOTO_ERRORS = (BotoCoreError, ClientError)
NOT_CONFIGURED = "dev-mode is not configured (set ARCHIVENETWORK_DYNAMODB_TABLE)"
REFUSE_AWS = (
    "Refusing to create or delete a table on real AWS; production tables come from "
    "Terraform (infra/)."
)


class TableRequest(BaseModel):
    reset: bool = False


def _require_table() -> str:
    if not settings.dynamodb_table:
        raise HTTPException(status_code=404, detail=NOT_CONFIGURED)
    return settings.dynamodb_table


def _table() -> dynamo.Table:
    _require_table()
    return dynamo.from_settings(settings)


def _unreachable(p: dynamo.Probe) -> HTTPException:
    return HTTPException(
        status_code=502, detail=f"Can't reach DynamoDB at {p.endpoint} — {p.reason}"
    )


def _boto_failed(exc: Exception, suffix: str = "") -> HTTPException:
    return HTTPException(status_code=502, detail=f"DynamoDB request failed — {exc}.{suffix}")


def _reachable_table() -> tuple[dynamo.Table, dynamo.Probe]:
    t = _table()
    p = dynamo.probe(t)
    if not p.endpoint_reachable:
        raise _unreachable(p)
    return t, p


def _ready_table() -> dynamo.Table:
    """The one guard load, rows and validate share: reachable, not refused, table present."""
    t, p = _reachable_table()
    if p.refused:
        raise HTTPException(status_code=502, detail=f"DynamoDB refused the request — {p.reason}")
    if not p.table_exists:
        raise HTTPException(status_code=409, detail="The table does not exist — create it first.")
    return t


def _store() -> LocalStorage:
    return LocalStorage(settings.media_root)


def _ready_root(request: Request) -> tuple[Path, str]:
    session = request.app.state.session
    if session is None:
        raise HTTPException(status_code=404, detail="No export loaded")
    root = settings.workspace_dir / "ready" / session.workspace_id
    if not (root / "posts").exists():
        raise HTTPException(
            status_code=409, detail="This workspace has not been built yet — run Build first."
        )
    return root, session.workspace_id


@router.get("/api/dev/status")
def status() -> dict:
    if not settings.dynamodb_table:
        return {
            "enabled": False,
            "endpoint_reachable": False,
            "table_exists": False,
            "reason": "ARCHIVENETWORK_DYNAMODB_TABLE is not set",
        }
    t = _table()
    p = dynamo.probe(t)
    reason = p.reason
    row_counts: dict[str, int] = {}
    if p.table_exists:
        try:
            row_counts = dynamo.counts(t)
        except _BOTO_ERRORS as exc:
            reason = str(exc)
    return {
        "enabled": True,
        **asdict(p),
        "reason": reason,
        "on_emulator": t.on_emulator,
        "counts": row_counts,
        "media_root": str(settings.media_root),
        "media_base_url": settings.media_base_url,
    }


@router.get("/api/dev/table")
def table_status() -> dict:
    """Is the endpoint up, and does the table exist? Never 500s on a stopped emulator."""
    return asdict(dynamo.probe(_table()))


@router.post("/api/dev/table")
def table_create(body: TableRequest | None = None) -> dict:
    t, _ = _reachable_table()
    reset = bool(body and body.reset)
    try:
        if reset:
            dynamo.delete_table(t)
        created = dynamo.create_table(t)
        row_counts = dynamo.counts(t)
    except dynamo.NotOnEmulator as exc:
        raise HTTPException(status_code=409, detail=REFUSE_AWS) from exc
    except _BOTO_ERRORS as exc:
        raise _boto_failed(exc) from exc
    return {**asdict(dynamo.probe(t)), "created": created, "reset": reset, "counts": row_counts}


@router.delete("/api/dev/table")
def table_delete() -> dict:
    """Destructive: drops the whole table, every item with it. Emulator only."""
    t, _ = _reachable_table()
    try:
        deleted = dynamo.delete_table(t)
    except dynamo.NotOnEmulator as exc:
        raise HTTPException(status_code=409, detail=REFUSE_AWS) from exc
    except _BOTO_ERRORS as exc:
        raise _boto_failed(exc) from exc
    return {**asdict(dynamo.probe(t)), "deleted": deleted}


@router.post("/api/dev/load")
def run_load(request: Request) -> dict:
    _require_table()
    root, workspace_id = _ready_root(request)
    t = _ready_table()
    try:
        result = load(root, workspace_id, _store(), t)
        row_counts = dynamo.counts(t)
    except _BOTO_ERRORS as exc:
        raise _boto_failed(exc, " Re-running the load is safe.") from exc
    return {
        "albums_inserted": result.albums_inserted,
        "albums_updated": result.albums_updated,
        "media_inserted": result.media_inserted,
        "media_updated": result.media_updated,
        "files_stored": result.files_stored,
        "files_skipped": result.files_skipped,
        "orphans": result.orphans,
        "errors": result.errors,
        "skipped_deleted": result.skipped_deleted,
        "counts": row_counts,
    }


@router.get("/api/dev/rows")
def rows(
    kind: Literal["media", "album"] = Query("media", alias="type"),
    limit: int = 50,
    offset: int = 0,
) -> dict:
    t = _ready_table()
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    try:
        items = dynamo.scan_items(t, kind)
    except _BOTO_ERRORS as exc:
        raise _boto_failed(exc) from exc
    return {
        "type": kind,
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "rows": items[offset:offset + limit],
    }


@router.get("/api/dev/validate")
def run_validate(request: Request) -> dict:
    _require_table()
    root, _ = _ready_root(request)
    t = _ready_table()
    try:
        checks = validate(root, _store(), t)
    except _BOTO_ERRORS as exc:
        raise _boto_failed(exc) from exc
    return {
        "ok": all(c.ok for c in checks),
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks],
    }
