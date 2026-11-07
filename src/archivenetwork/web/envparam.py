"""The `?env=` / `{name}` resolution and AWS-error mapping every env-scoped route shares.

Structured errors are top-level `{"error": <code>, ...}` bodies (contract C1), never FastAPI's
`{"detail": {...}}` wrapper: routes raise `ApiError` and the handler `install()` registers turns
it into a `JSONResponse` as is.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from botocore.exceptions import (
    NoCredentialsError,
    ProfileNotFound,
    SSOTokenLoadError,
    TokenRetrievalError,
    UnauthorizedSSOTokenError,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..loader.awsauth import SignedOut
from ..loader.envs import Env, UnknownEnv
from ..loader.load import CREDENTIAL_ERRORS, error_code

EXPIRED_DURING_PUBLISH = (
    "Your AWS login expired during Publish. Sign in again; re-running Publish is safe."
)
DENIED = frozenset({"AccessDenied", "AccessDeniedException", "403"})
# Profile envs fail inside botocore's own credential chain, before any request is sent.
_PROFILE_SIGNED_OUT = (
    NoCredentialsError, SSOTokenLoadError, TokenRetrievalError, UnauthorizedSSOTokenError,
)


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


def resolve_env(request: Request, name: str) -> Env:
    """A known, configured env, or the contract's 422 / 409."""
    env = lookup_env(request, name)
    if not env.configured:
        raise ApiError(409, {"error": "not_configured", "env": name})
    return env


def _message(exc: BaseException) -> str:
    resp = getattr(exc, "response", None) or {}
    return str(resp.get("Error", {}).get("Message") or exc)


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
    except _PROFILE_SIGNED_OUT as exc:
        raise signed_out() from exc
    except ProfileNotFound as exc:
        raise ApiError(409, {"error": "not_configured", "env": env.name}) from exc
    except Exception as exc:
        code = error_code(exc)
        if code in DENIED:
            raise ApiError(403, {"error": "access_denied", "detail": _message(exc)}) from exc
        # A bare "400" is how a HEAD reports an expired token: it has no body to name it.
        if code in CREDENTIAL_ERRORS or code == "400":
            raise signed_out() from exc
        raise
