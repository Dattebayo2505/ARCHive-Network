"""The `?env=` / `{name}` resolution and AWS-error mapping every env-scoped route shares.

Structured errors are top-level `{"error": <code>, ...}` bodies (contract C1), never FastAPI's
`{"detail": {...}}` wrapper: routes raise `ApiError` and the handler `install()` registers turns
it into a `JSONResponse` as is.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from botocore.exceptions import ProfileNotFound
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from ..loader.awsauth import NotAssigned, SignedOut
from ..loader.dynamo import CREDENTIAL_CHAIN_ERRORS
from ..loader.envs import Env, UnknownEnv
from ..loader.load import CREDENTIAL_ERRORS, error_code

EXPIRED_DURING_PUBLISH = (
    "Your AWS login expired during Publish. Sign in again; re-running Publish is safe."
)
DENIED = frozenset({"AccessDenied", "AccessDeniedException", "403"})
_PROFILE_SIGNED_OUT = CREDENTIAL_CHAIN_ERRORS
# The grants a bare-403 S3 call needs: a HEAD of a missing key without ListBucket is a 403 too.
_S3_NEEDS = {
    "HeadObject": "s3:GetObject and s3:ListBucket",
    "GetObject": "s3:GetObject",
    "PutObject": "s3:PutObject",
    "HeadBucket": "s3:ListBucket",
}


class ApiError(Exception):
    def __init__(self, status: int, body: dict) -> None:
        super().__init__(f"{status} {body}")
        self.status = status
        self.body = body


async def _handle(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(exc.body, status_code=exc.status)


def install(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle)


def lookup_env(request: Request, name: str) -> Env:
    try:
        return request.app.state.envs.get(name)
    except UnknownEnv:
        raise ApiError(422, {"error": "unknown_env", "env": name}) from None


def require_json(request: Request) -> None:
    """Refuse a write that isn't JSON (415). A bodiless or text/plain POST is a CORS "simple"
    request that needs no preflight, so any web page could send one; JSON forces the preflight."""
    ctype = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if ctype != "application/json":
        raise ApiError(415, {
            "error": "json_required",
            "detail": "Send a JSON body with Content-Type: application/json.",
        })


def aws_failed(env: Env, exc: Exception, safe: str = "Re-running is safe.") -> HTTPException:
    """A transport failure or unmapped AWS error: a 502 naming where, never an opaque 500."""
    where = "floci" if env.kind == "floci" else "AWS"
    return HTTPException(status_code=502, detail=f"{where} request failed — {exc}. {safe}")


def resolve_env(request: Request, name: str) -> Env:
    """A known, configured env, or the contract's 422 / 409."""
    env = lookup_env(request, name)
    if not env.configured:
        raise ApiError(409, {"error": "not_configured", "env": name})
    return env


def _message(exc: BaseException) -> str:
    resp = getattr(exc, "response", None) or {}
    return str(resp.get("Error", {}).get("Message") or exc)


def _denied_detail(exc: BaseException) -> str:
    """Name the action and resource (spec §5); a HEAD's bare 403 carries no message of its own."""
    if error_code(exc) != "403":
        return _message(exc)
    op = getattr(exc, "operation_name", None) or "The request"
    resource = getattr(exc, "resource", None)
    detail = f"{op} on {resource} was forbidden" if resource else f"{op} was forbidden"
    needs = _S3_NEEDS.get(op)
    return detail + (f" (needs {needs})" if needs else "")


@contextmanager
def aws_errors(env: Env, *, during_publish: bool = False) -> Iterator[None]:
    """Signed out / expired -> 401; a denial -> 403. Anything else passes through."""

    def signed_out() -> ApiError:
        body = {"error": "signed_out", "env": env.name}
        if during_publish:
            body["detail"] = EXPIRED_DURING_PUBLISH
        return ApiError(401, body)

    try:
        yield
    except SignedOut as exc:
        raise signed_out() from exc
    except NotAssigned as exc:
        raise ApiError(403, {"error": "access_denied", "detail": str(exc)}) from exc
    except _PROFILE_SIGNED_OUT as exc:
        raise signed_out() from exc
    except ProfileNotFound as exc:
        raise ApiError(409, {"error": "not_configured", "env": env.name}) from exc
    except Exception as exc:
        code = error_code(exc)
        if code in DENIED:
            raise ApiError(403, {"error": "access_denied", "detail": _denied_detail(exc)}) from exc
        # A bare "400" is how a HEAD reports an expired token: it has no body to name it.
        if code in CREDENTIAL_ERRORS or code == "400":
            raise signed_out() from exc
        raise
