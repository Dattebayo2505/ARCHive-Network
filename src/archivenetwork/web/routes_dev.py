"""Dev-mode: run the real ETL against a local Postgres + local object store.

Every route here 404s unless `settings.database_url` is set. The frontend toggle only *reveals*
the panel — the backend decides whether dev-mode is usable.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..config import settings
from ..loader import db
from ..loader.load import load
from ..loader.storage import LocalStorage
from ..loader.validate import validate

router = APIRouter()


class SchemaRequest(BaseModel):
    reset: bool = False


def _require_db() -> str:
    if not settings.database_url:
        raise HTTPException(
            status_code=404,
            detail="dev-mode is not configured (set ARCHIVENETWORK_DATABASE_URL)",
        )
    return settings.database_url


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
    if not settings.database_url:
        return {
            "enabled": False,
            "connected": False,
            "reason": "ARCHIVENETWORK_DATABASE_URL is not set",
        }
    try:
        with db.connect(settings.database_url) as conn:
            ready = db.tables_exist(conn)
            row_counts = db.counts(conn) if ready else {}
    except psycopg.Error as exc:
        # A failure here is ambiguous on its face — "server down" and "database missing" are
        # the same libpq error. Probe the server so the UI can offer the right next step
        # (start Postgres vs. press Create database) instead of just printing the error.
        found = db.probe(settings.database_url)
        return {
            "enabled": True,
            "connected": False,
            "reason": str(exc),
            "server_up": found.server_up,
            "database": found.database,
            "database_exists": found.database_exists,
        }
    return {
        "enabled": True,
        "connected": True,
        "server_up": True,
        "database": db.database_name(settings.database_url),
        "database_exists": True,
        "tables_exist": ready,
        "counts": row_counts,
        "media_root": str(settings.media_root),
        "media_base_url": settings.media_base_url,
    }


def _database_state() -> dict:
    found = db.probe(_require_db())
    return {
        "server_up": found.server_up,
        "database": found.database,
        "database_exists": found.database_exists,
        "reason": found.reason,
    }


@router.get("/api/dev/database")
def database_status() -> dict:
    """Is the server up, and does our database exist? Never 500s on a down server."""
    return _database_state()


@router.post("/api/dev/database")
def database_create() -> dict:
    url = _require_db()
    found = db.probe(url)
    if not found.server_up:
        raise HTTPException(
            status_code=502, detail=f"Can't reach the PostgreSQL server — {found.reason}"
        )
    created = db.create_database(url)
    return {**_database_state(), "created": created}


@router.delete("/api/dev/database")
def database_drop() -> dict:
    """Destructive — drops the whole database, tables and rows with it. Dev only."""
    url = _require_db()
    found = db.probe(url)
    if not found.server_up:
        raise HTTPException(
            status_code=502, detail=f"Can't reach the PostgreSQL server — {found.reason}"
        )
    dropped = db.drop_database(url)
    return {**_database_state(), "dropped": dropped}


@router.post("/api/dev/schema")
def schema(body: SchemaRequest | None = None) -> dict:
    url = _require_db()
    reset = bool(body and body.reset)
    with db.connect(url) as conn:
        if reset:
            db.reset_tables(conn)
        else:
            db.create_tables(conn)
        return {"tables_exist": db.tables_exist(conn), "reset": reset, "counts": db.counts(conn)}


@router.post("/api/dev/load")
def run_load(request: Request) -> dict:
    url = _require_db()
    root, workspace_id = _ready_root(request)
    with db.connect(url) as conn:
        if not db.tables_exist(conn):
            raise HTTPException(status_code=409, detail="Tables do not exist — create them first.")
        result = load(root, workspace_id, _store(), conn)
        return {
            "albums_inserted": result.albums_inserted,
            "albums_updated": result.albums_updated,
            "media_inserted": result.media_inserted,
            "media_updated": result.media_updated,
            "files_stored": result.files_stored,
            "files_skipped": result.files_skipped,
            "orphans": result.orphans,
            "errors": result.errors,
            "counts": db.counts(conn),
        }


@router.get("/api/dev/rows")
def rows(table: str = "media", limit: int = 50, offset: int = 0) -> dict:
    url = _require_db()
    if table not in {"media", "photo_album"}:
        raise HTTPException(status_code=400, detail="table must be 'media' or 'photo_album'")
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    with db.connect(url) as conn, conn.cursor() as cur:
        # `table` is allow-listed above, so the interpolation cannot carry user input.
        cur.execute(f"SELECT count(*) FROM {table}")
        total = cur.fetchone()[0]
        cur.execute(f"SELECT * FROM {table} ORDER BY 1 LIMIT %s OFFSET %s", (limit, offset))
        columns = [c.name for c in cur.description]
        data = [dict(zip(columns, r)) for r in cur.fetchall()]
    return {"table": table, "total": total, "limit": limit, "offset": offset, "rows": data}


@router.get("/api/dev/validate")
def run_validate(request: Request) -> dict:
    url = _require_db()
    root, _ = _ready_root(request)
    with db.connect(url) as conn:
        if not db.tables_exist(conn):
            raise HTTPException(status_code=409, detail="Tables do not exist — create them first.")
        checks = validate(root, _store(), conn)
    return {
        "ok": all(c.ok for c in checks),
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks],
    }
