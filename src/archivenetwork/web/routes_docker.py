"""Start / restart / stop / rebuild the local floci container from the Dev panel.

Independent of any environment's tables or bucket: no database, no
session, no export required — the container is a machine-level thing, and asking a volunteer
to have a workspace open before they may restart Docker would be theatre.

The split mirrors `GET` vs `POST /api/dev/tables`: `GET /api/docker/status` answers
*can we*, and only then does the panel offer the verbs. `POST` refuses with a 409 when it
can't, so a stale frontend can never turn a missing binary into a 500.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..loader import dockerctl, flociui, flociversion
from ..loader.dockerctl import Action

router = APIRouter()


def _floci_endpoint(request: Request) -> str:
    """The default env's emulator: the one floci the Docker controls manage."""
    return request.app.state.envs.floci().endpoint_url


@router.get("/api/docker/floci-version")
def floci_version(request: Request) -> dict:
    """Running vs pinned vs latest floci (`loader/flociversion.py`). Never fails: an
    unreachable floci or GitHub comes back as `null` fields with a status explaining it."""
    return flociversion.report(_floci_endpoint(request), dockerctl.COMPOSE_FILE).as_dict()


@router.get("/api/docker/floci-ui")
def ui(request: Request) -> dict:
    """Where to send someone who wants to look at the bucket.

    Lives here rather than in the browser because the two calls involved are cross-origin to
    floci, which sends no CORS headers: a `no-cors` fetch would perform the warm-up but could
    never read back whether it worked. Never fails — an unreachable floci comes back as
    `ready: false` with the poller URL, which is always safe to open.

    The wait budget is not a query parameter: no caller passes one, and a caller-controlled
    sleep on a server route is a lever with no user. `flociui.DEFAULT_WAIT` owns it.
    """
    return flociui.ensure(_floci_endpoint(request)).as_dict()


@router.get("/api/docker/status")
def status() -> dict:
    """Never 404s and never fails: an unusable Docker is a *reading*, not an error."""
    return dockerctl.probe().as_dict()


@router.post("/api/docker/floci")
def act(action: Action) -> dict:
    """`action` is REQUIRED — a bare Literal with no default, exactly like `/api/publish`'s
    `env`. A typo is a 422, never a silently-chosen lifecycle command."""
    state = dockerctl.probe()
    if not state.available:
        raise HTTPException(
            status_code=409,
            detail=state.reason
            or (
                "docker-compose.yml is missing from the repo root."
                if not state.compose_file
                else "Docker isn't available."
            ),
        )

    outcome = dockerctl.run_action(action)
    # The post-action reading is the point: the panel re-renders from `docker`'s own view of
    # the container, not from an assumption about what the verb should have done.
    after = dockerctl.probe()
    return {
        "action": action,
        "ok": outcome.ok,
        "code": outcome.code,
        "output": outcome.output,
        "docker": after.as_dict(),
    }
