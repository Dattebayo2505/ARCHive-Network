"""On-demand S3 upload. Gated on `settings.s3_bucket` (independent of dev-mode/Postgres).

Pushes the current built workspace's ready folder to AWS S3 under the same canonical keys
the local store uses. No DB involvement — this is an object-store op, so (like auto-curate)
it lives outside the DB-gated dev routes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
)
from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..loader.storage import S3Storage, probe_endpoint
from ..loader.upload import upload_ready

router = APIRouter()

Target = Literal["aws", "floci"]

# Not secrets and not configurable: floci ignores credentials, but boto3 requires a pair and
# S3Storage only forwards them both-or-neither.
FLOCI_ACCESS_KEY_ID = "test"
FLOCI_SECRET_ACCESS_KEY = "test"


def _require_target(target: Target) -> None:
    """AWS needs a configured bucket; floci always has one (its settings have defaults)."""
    if target == "aws" and not settings.s3_bucket:
        raise HTTPException(
            status_code=404,
            detail="S3 is not configured (set ARCHIVENETWORK_S3_BUCKET)",
        )


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


def _store(target: Target) -> S3Storage:
    if target == "floci":
        return S3Storage(
            settings.floci_bucket,
            settings.s3_region,
            FLOCI_ACCESS_KEY_ID,
            FLOCI_SECRET_ACCESS_KEY,
            endpoint_url=settings.floci_endpoint_url,
            # Floci starts empty; the AWS branch below must never do this.
            create_if_missing=True,
        )
    return S3Storage(
        settings.s3_bucket,
        settings.s3_region,
        settings.s3_access_key_id,
        settings.s3_secret_access_key,
    )


@router.get("/api/s3/status")
def status() -> dict:
    aws: dict = {"enabled": False}
    if settings.s3_bucket:
        aws = {"enabled": True, "bucket": settings.s3_bucket, "region": settings.s3_region}
    probe = probe_endpoint(settings.floci_endpoint_url)
    return {
        "aws": aws,
        "floci": {
            "enabled": True,
            "bucket": settings.floci_bucket,
            "region": settings.s3_region,
            "endpoint_url": settings.floci_endpoint_url,
            "reachable": probe.reachable,
            "reason": probe.reason,
        },
    }


@router.post("/api/s3/upload")
def upload(request: Request) -> dict:
    # Temporarily pinned to "aws" so this commit stays green. Task 5 makes it a required
    # request parameter.
    _require_target("aws")
    root, _ = _ready_root(request)
    try:
        result = upload_ready(root, _store("aws"))
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
