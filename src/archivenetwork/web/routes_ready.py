from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..config import settings
from ..reveal import RevealError, reveal_path
from ..transform.ready_index import scan_ready_builds

router = APIRouter()


class RevealBuildRequest(BaseModel):
    id: str


def _ready_root():
    return settings.workspace_dir / "ready"


@router.get("/api/ready")
def list_ready(request: Request) -> dict:
    builds = scan_ready_builds(_ready_root())
    return {"builds": [asdict(b) for b in builds]}


@router.post("/api/ready/reveal")
def reveal_ready(body: RevealBuildRequest) -> dict:
    ready_root = _ready_root().resolve()
    target = (ready_root / body.id).resolve()
    # Path-safety: the target must be a *direct* child of ready_root that exists.
    # A traversal id ("..") or an absolute path resolves elsewhere and is rejected —
    # reveal must never open a folder outside workspace/ready/.
    if target.parent != ready_root or not target.is_dir():
        raise HTTPException(status_code=404, detail="No such build")
    try:
        reveal_path(target)
    except RevealError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True}
