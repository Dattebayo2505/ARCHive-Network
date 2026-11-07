"""The environment list and app-scoped sign-in (spec §5, contract C2/C3).

`GET /api/envs` never fails on an AWS problem: a signed-in env whose identity can't be read just
has `identity: null`. It never carries an SSO start URL, account ID or profile name.
"""

from __future__ import annotations

from dataclasses import asdict

from botocore.exceptions import BotoCoreError, ClientError, ProfileNotFound
from fastapi import APIRouter, HTTPException, Request

from ..loader import envclients
from ..loader.awsauth import SignedOut
from ..loader.dynamo import CREDENTIAL_CHAIN_ERRORS
from ..loader.envs import Env
from .envparam import ApiError, aws_errors, lookup_env, resolve_env

router = APIRouter()


def _entry(env: Env, auth) -> dict:
    out = env.public()
    if env.kind == "floci":
        return {**out, "signed_in": True, "login": "signed_in", "identity": "floci"}
    login, identity = "signed_out", None
    if env.configured:
        try:
            login = auth.state(env)
        except ProfileNotFound:
            # Every action 409s not_configured for it (CA7), so the list says the same.
            out["configured"] = False
        except Exception:  # a sign-in problem must not take the env list down with it
            login = "signed_out"
        if login == "signed_in":
            try:
                identity = envclients.identity_for(env, auth)[0]
            except (SignedOut, *CREDENTIAL_CHAIN_ERRORS):
                # A profile's SSO credentials are deferred: only a real call shows they expired.
                login = "signed_out"
            except Exception:  # e.g. NotAssigned: signed in, but no role; Publish names it (403)
                identity = None
    return {**out, "signed_in": login == "signed_in", "login": login, "identity": identity}


@router.get("/api/envs")
def list_envs(request: Request) -> dict:
    reg = request.app.state.envs
    auth = request.app.state.auth
    return {
        "default": reg.default,
        "envs": [_entry(env, auth) for env in reg.envs.values()],
        "stale_settings": list(getattr(request.app.state, "stale_settings", [])),
        "errors": list(reg.errors),
    }


def _sso_env(request: Request, name: str) -> Env:
    env = resolve_env(request, name)
    if env.kind == "floci":
        raise ApiError(409, {"error": "no_login", "env": name})
    if env.profile:
        raise ApiError(409, {"error": "profile_login",
                             "detail": f"Run: aws sso login --profile {env.profile}"})
    return env


def _sign_in_failed(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=f"AWS sign-in request failed — {exc}")


@router.post("/api/envs/{name}/login")
def start_login(request: Request, name: str) -> dict:
    env = _sso_env(request, name)
    try:
        with aws_errors(env):
            return asdict(request.app.state.auth.start_login(env))
    except (ClientError, BotoCoreError) as exc:
        raise _sign_in_failed(exc) from exc


@router.get("/api/envs/{name}/login")
def poll_login(request: Request, name: str) -> dict:
    env = resolve_env(request, name)
    if env.kind == "floci":
        return {"state": "signed_in"}
    try:
        with aws_errors(env):
            return {"state": request.app.state.auth.poll_login(env)}
    except (ClientError, BotoCoreError) as exc:
        raise _sign_in_failed(exc) from exc


@router.post("/api/envs/{name}/logout")
def logout(request: Request, name: str) -> dict:
    env = lookup_env(request, name)
    if env.kind == "floci":
        raise ApiError(409, {"error": "no_login", "env": name})
    request.app.state.auth.logout(env)
    return {"state": "signed_out"}
