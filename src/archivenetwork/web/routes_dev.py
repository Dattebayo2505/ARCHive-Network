"""Dev-mode: run the real ETL against the per-type DynamoDB tables (floci locally) + a local store.

Every route here 404s unless `settings.dynamodb_table_prefix` is set. The frontend toggle only
*reveals* the panel; the backend decides whether dev-mode is usable. `/api/dev/tables` probes,
creates (or resets) and deletes all 11 tables; load, rows and validate need every probed table.

Handlers call `_tables()` in their bodies, never through `Depends`: tests monkeypatch the module
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
NOT_SET = "ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX is not set"
NOT_CONFIGURED = "dev-mode is not configured (set ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX)"
RENAMED = (
    "ARCHIVENETWORK_DYNAMODB_TABLE was replaced by ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX "
    "(e.g. archers-network-dev)"
)
REFUSE_AWS = (
    "Refusing to create or delete tables on real AWS; production tables come from "
    "Terraform (infra/)."
)


class TableRequest(BaseModel):
    reset: bool = False


def _require_prefix() -> str:
    if not settings.dynamodb_table_prefix:
        raise HTTPException(status_code=404, detail=NOT_CONFIGURED)
    return settings.dynamodb_table_prefix


def _tables() -> dynamo.Tables:
    _require_prefix()
    return dynamo.from_settings(settings)


def _unreachable(p: dynamo.Probe) -> HTTPException:
    return HTTPException(
        status_code=502, detail=f"Can't reach DynamoDB at {p.endpoint} — {p.reason}"
    )


def _boto_failed(exc: Exception, suffix: str = "") -> HTTPException:
    return HTTPException(status_code=502, detail=f"DynamoDB request failed — {exc}.{suffix}")


def _reachable_tables() -> tuple[dynamo.Tables, dynamo.Probe]:
    t = _tables()
    p = dynamo.probe(t)
    if not p.endpoint_reachable:
        raise _unreachable(p)
    return t, p


def _ready_tables() -> dynamo.Tables:
    """The one guard load, rows and validate share: reachable, not refused, no table missing."""
    t, p = _reachable_tables()
    if p.refused:
        raise HTTPException(status_code=502, detail=f"DynamoDB refused the request — {p.reason}")
    if not p.table_exists:
        names = ", ".join(p.tables[k] for k in p.missing)
        raise HTTPException(status_code=409, detail=f"Missing tables: {names} — create them first.")
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
    if not settings.dynamodb_table_prefix:
        # An old .env still naming the single table must not read as "never configured".
        reason = RENAMED if settings.dynamodb_table else NOT_SET
        return {
            "enabled": False,
            "endpoint_reachable": False,
            "table_exists": False,
            "reason": reason,
        }
    t = _tables()
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


@router.get("/api/dev/tables")
def tables_status() -> dict:
    """Is the endpoint up, and which tables exist? Never 500s on a stopped emulator."""
    return asdict(dynamo.probe(_tables()))


@router.post("/api/dev/tables")
def tables_create(body: TableRequest | None = None) -> dict:
    """Create the missing tables (only those), or with `reset` drop and recreate all 11."""
    t, _ = _reachable_tables()
    reset = bool(body and body.reset)
    try:
        if reset:
            dynamo.delete_tables(t)
        created = dynamo.create_tables(t)
        row_counts = dynamo.counts(t)
    except dynamo.NotOnEmulator as exc:
        raise HTTPException(status_code=409, detail=REFUSE_AWS) from exc
    except _BOTO_ERRORS as exc:
        raise _boto_failed(exc) from exc
    return {**asdict(dynamo.probe(t)), "created": created, "reset": reset, "counts": row_counts}


@router.delete("/api/dev/tables")
def tables_delete() -> dict:
    """Destructive: drops all 11 tables, every item with them. Emulator only."""
    t, _ = _reachable_tables()
    try:
        deleted = dynamo.delete_tables(t)
    except dynamo.NotOnEmulator as exc:
        raise HTTPException(status_code=409, detail=REFUSE_AWS) from exc
    except _BOTO_ERRORS as exc:
        raise _boto_failed(exc) from exc
    return {**asdict(dynamo.probe(t)), "deleted": deleted}


@router.post("/api/dev/load")
def run_load(request: Request) -> dict:
    _require_prefix()
    root, workspace_id = _ready_root(request)
    t = _ready_tables()
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
    t = _ready_tables()
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
    _require_prefix()
    root, _ = _ready_root(request)
    t = _ready_tables()
    try:
        checks = validate(root, _store(), t)
    except _BOTO_ERRORS as exc:
        raise _boto_failed(exc) from exc
    return {
        "ok": all(c.ok for c in checks),
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks],
    }
