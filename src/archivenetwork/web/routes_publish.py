"""One-click Publish: the built ready folder to one env's bucket and tables, then verified.

`env` is a required query param: a forgotten one is a 422, never an implicit write. A `confirm`
env (prod) needs the body `{"confirm": "<env name>"}`, exact and case-sensitive; the frontend's
type-to-confirm dialog sends it, and this check is its backstop against a stale tab or a
hand-made request. One Publish per env at a time: a second one is a 409, not an interleaved load.

`_clients` is called in the handler body, never via `Depends`, so tests can patch it.
"""

from __future__ import annotations

import threading
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ..config import settings
from ..loader import dynamo, envclients, publish
from ..loader.envs import Env
from ..loader.storage import S3Storage
from .envparam import ApiError, aws_errors, aws_failed, require_json, resolve_env

router = APIRouter()

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class PublishRequest(BaseModel):
    confirm: str | None = None


def _lock_for(name: str) -> threading.Lock:
    """The per-env lock a running Publish holds."""
    with _locks_guard:
        return _locks.setdefault(name, threading.Lock())


def _clients(env: Env, auth) -> tuple[S3Storage, dynamo.Tables, tuple[str, str]]:
    return envclients.clients_for(env, auth)


def ready_root(request: Request) -> tuple[Path, str]:
    """The session's built ready folder, or the 404 / 409 the panel already knows."""
    session = request.app.state.session
    if session is None:
        raise HTTPException(status_code=404, detail="No export loaded")
    root = settings.workspace_dir / "ready" / session.workspace_id
    if not (root / "posts").exists():
        raise HTTPException(
            status_code=409, detail="This workspace has not been built yet — run Build first."
        )
    return root, session.workspace_id


@router.post("/api/publish")
def run_publish(
    request: Request, env: str = Query(...), body: PublishRequest | None = None
) -> dict:
    require_json(request)
    target = resolve_env(request, env)
    root, workspace_id = ready_root(request)
    if target.confirm and (body is None or body.confirm != target.name):
        raise ApiError(409, {"error": "confirm_required", "env": target.name})

    lock = _lock_for(target.name)
    if not lock.acquire(blocking=False):
        raise ApiError(409, {"error": "publish_running", "env": target.name})
    try:
        # Building the clients calls SSO / STS, so a bad network fails here as well as mid-run.
        # Each item is atomic and bytes go first, so either way a re-run converges.
        try:
            with aws_errors(target):
                storage, tables, identity = _clients(target, request.app.state.auth)
            with aws_errors(target, during_publish=True):
                result = publish.publish(root, workspace_id, target, storage, tables, identity)
        except (BotoCoreError, ClientError) as exc:
            raise aws_failed(target, exc, "Re-running Publish is safe.") from exc
    finally:
        lock.release()
    return result.as_dict()
