"""On-demand S3 upload. Gated on `settings.s3_bucket` (independent of dev-mode/Postgres).

Pushes the current built workspace's ready folder to AWS S3 under the same canonical keys
the local store uses. No DB involvement — this is an object-store op, so (like auto-curate)
it lives outside the DB-gated dev routes.
"""

from __future__ import annotations

from pathlib import Path

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
)
from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..loader.storage import S3Storage
from ..loader.upload import upload_ready

router = APIRouter()


def _require_s3() -> str:
    if not settings.s3_bucket:
        raise HTTPException(
            status_code=404,
            detail="S3 is not configured (set ARCHIVENETWORK_S3_BUCKET)",
        )
    return settings.s3_bucket


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


def _store() -> S3Storage:
    return S3Storage(
        settings.s3_bucket,
        settings.s3_region,
        settings.s3_access_key_id,
        settings.s3_secret_access_key,
    )


@router.get("/api/s3/status")
def status() -> dict:
    if not settings.s3_bucket:
        return {"enabled": False}
    return {"enabled": True, "bucket": settings.s3_bucket, "region": settings.s3_region}


@router.post("/api/s3/upload")
def upload(request: Request) -> dict:
    _require_s3()
    root, _ = _ready_root(request)
    try:
        result = upload_ready(root, _store())
    except (ClientError, NoCredentialsError, EndpointConnectionError, BotoCoreError) as exc:
        # A whole-run blocker surfaced by the preflight head_bucket inside upload_ready.
        raise HTTPException(status_code=502, detail=f"S3 not reachable: {exc}") from exc
    return {
        "uploaded": result.uploaded,
        "skipped": result.skipped,
        "orphans": result.orphans,
        "errors": result.errors,
        "bucket": settings.s3_bucket,
        "region": settings.s3_region,
    }
