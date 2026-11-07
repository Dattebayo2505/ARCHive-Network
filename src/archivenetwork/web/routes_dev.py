"""Dev-mode: inspect one named environment's tables and bucket.

Every route takes a required `?env=` and works on that env's `Tables` and `S3Storage`, so the
panel's reading and its Publish always point at the same place. `/api/dev/tables` probes, creates
(or resets) and deletes all 11 tables, on an emulator only; rows and validate need every probed
table. Publishing lives in `routes_publish`.

Handlers call `_tables()` / `_storage()` in their bodies, never through `Depends`: tests
monkeypatch the module attributes, and a `Depends` reference would silently bypass the patch.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ..loader import dynamo, envclients
from ..loader.envs import Env
from ..loader.load import CREDENTIAL_ERRORS
from ..loader.storage import S3Storage
from ..loader.validate import validate
from .envparam import DENIED, ApiError, aws_errors, aws_failed, require_json, resolve_env
from .routes_publish import ready_root

router = APIRouter()

_BOTO_ERRORS = (BotoCoreError, ClientError)
REFUSE_AWS = (
    "Refusing to create or delete tables on real AWS; AWS tables are created by hand per the "
    "AWS guide."
)
PREVIEW_SECONDS = 900


class TableRequest(BaseModel):
    reset: bool = False


def _tables(env: Env, auth) -> dynamo.Tables:
    return envclients.tables_for(env, auth)


def _storage(env: Env, auth) -> S3Storage:
    return envclients.storage_for(env, auth)


def _unreachable(p: dynamo.Probe) -> HTTPException:
    return HTTPException(
        status_code=502, detail=f"Can't reach DynamoDB at {p.endpoint} — {p.reason}"
    )


def _boto_failed(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=f"DynamoDB request failed — {exc}.")


def _env_tables(request: Request, name: str) -> tuple[Env, dynamo.Tables]:
    env = resolve_env(request, name)
    try:
        with aws_errors(env):
            return env, _tables(env, request.app.state.auth)
    except _BOTO_ERRORS as exc:  # SSO / STS run here: offline must be a 502, never a 500
        raise aws_failed(env, exc) from exc


def _probe(env: Env, t: dynamo.Tables) -> dynamo.Probe:
    """The probe, with an expired profile login (which it raises) mapped to the 401."""
    with aws_errors(env):
        return dynamo.probe(t)


def _refusal(env: Env, p: dynamo.Probe) -> None:
    """CA5: a refused probe whose code is a login or grant problem is the panel's 401 / 403."""
    # The probe flattens the error to "<Code>: <message>".
    code, _, message = (p.reason or "").partition(":")
    if code in DENIED:
        raise ApiError(403, {"error": "access_denied", "detail": message.strip()})
    if code in CREDENTIAL_ERRORS:
        raise ApiError(401, {"error": "signed_out", "env": env.name})


def _reachable_tables(request: Request, name: str) -> tuple[Env, dynamo.Tables, dynamo.Probe]:
    env, t = _env_tables(request, name)
    p = _probe(env, t)
    if not p.endpoint_reachable:
        raise _unreachable(p)
    return env, t, p


def _ready_tables(request: Request, name: str) -> tuple[Env, dynamo.Tables]:
    """The one guard rows and validate share: reachable, not refused, no table missing."""
    env, t, p = _reachable_tables(request, name)
    if p.refused:
        _refusal(env, p)
        raise HTTPException(status_code=502, detail=f"DynamoDB refused the request — {p.reason}")
    if not p.table_exists:
        names = ", ".join(p.tables[k] for k in p.missing)
        raise HTTPException(status_code=409, detail=f"Missing tables: {names} — create them first.")
    return env, t


@router.get("/api/dev/status")
def status(request: Request, env: str = Query(...)) -> dict:
    target, t = _env_tables(request, env)
    p = _probe(target, t)
    if p.refused:
        _refusal(target, p)  # any other refusal is a reading the card renders, so still a 200
    reason = p.reason
    row_counts: dict[str, int] = {}
    if p.table_exists:
        try:
            with aws_errors(target):
                row_counts = dynamo.counts(t)
        except _BOTO_ERRORS as exc:
            reason = str(exc)
    return {
        # Always true now that envs are committed; kept so `enabled && endpoint_reachable`
        # still reads as "connected" in the panel.
        "enabled": True,
        **asdict(p),
        "reason": reason,
        "on_emulator": t.on_emulator,
        "counts": row_counts,
        "env": target.name,
        "kind": target.kind,
    }


@router.get("/api/dev/tables")
def tables_status(request: Request, env: str = Query(...)) -> dict:
    """Is the endpoint up, and which tables exist? Never 500s on a stopped emulator."""
    target, t = _env_tables(request, env)
    return asdict(_probe(target, t))


@router.post("/api/dev/tables")
def tables_create(
    request: Request, env: str = Query(...), body: TableRequest | None = None
) -> dict:
    """Create the missing tables (only those), or with `reset` drop and recreate all 11."""
    require_json(request)
    target, t, _ = _reachable_tables(request, env)
    reset = bool(body and body.reset)
    try:
        with aws_errors(target):
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
def tables_delete(request: Request, env: str = Query(...)) -> dict:
    """Destructive: drops all 11 tables, every item with them. Emulator only."""
    target, t, _ = _reachable_tables(request, env)
    try:
        with aws_errors(target):
            deleted = dynamo.delete_tables(t)
    except dynamo.NotOnEmulator as exc:
        raise HTTPException(status_code=409, detail=REFUSE_AWS) from exc
    except _BOTO_ERRORS as exc:
        raise _boto_failed(exc) from exc
    return {**asdict(dynamo.probe(t)), "deleted": deleted}


@router.get("/api/dev/rows")
def rows(
    request: Request,
    env: str = Query(...),
    kind: Literal["media", "album"] = Query("media", alias="type"),
    limit: int = 50,
    offset: int = 0,
) -> dict:
    target, t = _ready_tables(request, env)
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    try:
        with aws_errors(target):
            items = dynamo.scan_items(t, kind)
            page = items[offset:offset + limit]
            if kind == "media":
                # Buckets are private, so each row renders through a short-lived presigned GET.
                store = _storage(target, request.app.state.auth)
                for item in page:
                    if item.get("storage_path"):
                        item["preview_url"] = store.presign(item["storage_path"], PREVIEW_SECONDS)
    except _BOTO_ERRORS as exc:
        raise _boto_failed(exc) from exc
    return {"type": kind, "total": len(items), "limit": limit, "offset": offset, "rows": page}


@router.get("/api/dev/validate")
def run_validate(request: Request, env: str = Query(...)) -> dict:
    target = resolve_env(request, env)
    root, _ = ready_root(request)
    _, t = _ready_tables(request, env)
    try:
        with aws_errors(target):
            checks = validate(root, _storage(target, request.app.state.auth), t)
    except _BOTO_ERRORS as exc:
        raise _boto_failed(exc) from exc
    return {
        "ok": all(c.ok for c in checks),
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks],
    }
