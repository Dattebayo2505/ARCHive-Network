"""`/api/envs` and the sign-in routes, on a registry built from tmp TOML and a fake AuthManager."""

from __future__ import annotations

from pathlib import Path

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from archivenetwork.app import create_app
from archivenetwork.loader.awsauth import DeviceLogin, SignedOut
from archivenetwork.loader.envs import load_registry
from archivenetwork.web import envparam, routes_envs

START_URL = "https://d-secret123.awsapps.com/start"
ACCOUNT = "111122223333"

COMMITTED = f"""
default = "local"

[env.local]
kind = "floci"
label = "Local (floci)"
endpoint_url = "http://127.0.0.1:1"
region = "ap-southeast-1"
s3_bucket = "local-bucket"
table_prefix = "an-local"

[env.dev]
kind = "aws"
label = "Dev (AWS)"
region = "ap-southeast-1"
s3_bucket = "dev-bucket"
table_prefix = "an-dev"
[env.dev.sso]
start_url = "{START_URL}"
region = "ap-southeast-1"
account_id = "{ACCOUNT}"
role_name = "Curators"

[env.prod]
kind = "aws"
label = "Prod (AWS)"
region = "ap-southeast-1"
s3_bucket = "prod-bucket"
table_prefix = "an-prod"
confirm = true
[env.prod.sso]
start_url = ""
region = "ap-southeast-1"
account_id = ""
role_name = "Curators"

[env.prof]
kind = "aws"
label = "Profile"
region = "ap-southeast-1"
s3_bucket = "prof-bucket"
table_prefix = "an-prof"
profile = "my-cli-profile"
"""


class FakeAuth:
    def __init__(self):
        self.states: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []

    def state(self, env):
        self.calls.append(("state", env.name))
        return "signed_in" if env.kind == "floci" else self.states.get(env.name, "signed_out")

    def start_login(self, env):
        self.calls.append(("start_login", env.name))
        self.states[env.name] = "pending"
        return DeviceLogin("https://device.sso/?user_code=ABCD", "ABCD", 600, 5)

    def poll_login(self, env):
        self.calls.append(("poll_login", env.name))
        state = self.states.get(env.name, "signed_out")
        if state == "pending":
            self.states[env.name] = "signed_in"
        return state

    def logout(self, env):
        self.calls.append(("logout", env.name))
        self.states[env.name] = "signed_out"

    def session(self, env):
        raise AssertionError("routes_envs must reach AWS through envclients.identity_for")


def registry(tmp_path: Path, overlay: str | None = None):
    committed = tmp_path / "environments.toml"
    committed.write_text(COMMITTED, encoding="utf-8")
    local = None
    if overlay is not None:
        local = tmp_path / "environments.local.toml"
        local.write_text(overlay, encoding="utf-8")
    return load_registry(committed, local)


@pytest.fixture
def auth():
    return FakeAuth()


@pytest.fixture
def identities(monkeypatch):
    seen: dict = {}

    def identity_for(env, auth):
        result = seen.get(env.name, ("arn:aws:sts::111122223333:assumed-role/Curators/u", ACCOUNT))
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(routes_envs.envclients, "identity_for", identity_for)
    return seen


@pytest.fixture
def client(tmp_path, auth, identities, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    app = create_app()
    app.state.envs = registry(tmp_path)
    app.state.auth = auth
    app.state.stale_settings = ["ARCHIVENETWORK_S3_BUCKET"]
    return TestClient(app)


def _by_name(body) -> dict:
    return {e["name"]: e for e in body["envs"]}


def test_app_state_has_an_auth_manager_under_the_workspace(tmp_path, monkeypatch):
    from archivenetwork.config import settings
    from archivenetwork.loader.awsauth import AuthManager

    app = create_app()
    assert isinstance(app.state.auth, AuthManager)
    assert app.state.auth.cache_dir == settings.workspace_dir / "aws" / "sso"


def test_list_shape(client, auth):
    auth.states["dev"] = "signed_in"
    resp = client.get("/api/envs")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"default", "envs", "stale_settings", "errors"}
    assert body["default"] == "local"
    assert body["stale_settings"] == ["ARCHIVENETWORK_S3_BUCKET"]
    assert body["errors"] == []
    envs = _by_name(body)
    assert [e["name"] for e in body["envs"]] == ["local", "dev", "prod", "prof"]
    assert envs["local"]["signed_in"] is True
    assert envs["local"]["login"] == "signed_in"
    assert envs["local"]["identity"] == "floci"
    assert envs["local"]["endpoint_url"] == "http://127.0.0.1:1"
    assert envs["dev"]["signed_in"] is True
    assert envs["dev"]["identity"].startswith("arn:aws:sts::")
    assert envs["dev"]["configured"] is True
    assert envs["prod"]["configured"] is False
    assert envs["prod"]["signed_in"] is False
    assert envs["prod"]["login"] == "signed_out"
    assert envs["prod"]["identity"] is None
    assert envs["prod"]["confirm"] is True
    for name in ("dev", "prod", "prof"):
        assert "endpoint_url" not in envs[name]
        assert "sso" not in envs[name] and "profile" not in envs[name]


def test_list_never_carries_sign_in_values(client, auth, identities):
    identities["dev"] = ("arn:aws:sts::assumed-role/Curators/u", "")  # no account in the arn
    auth.states["dev"] = "signed_in"
    text = client.get("/api/envs").text
    assert START_URL not in text
    assert "awsapps" not in text
    assert ACCOUNT not in text
    assert "my-cli-profile" not in text
    assert "account_id" not in text and "start_url" not in text


def test_list_signed_out_env_has_no_identity(client, auth):
    envs = _by_name(client.get("/api/envs").json())
    assert envs["dev"]["signed_in"] is False
    assert envs["dev"]["login"] == "signed_out"
    assert envs["dev"]["identity"] is None


def test_identity_failure_is_not_an_error_response(client, auth, identities):
    auth.states["dev"] = "signed_in"
    identities["dev"] = ClientError({"Error": {"Code": "InternalError", "Message": "x"}}, "Get")
    resp = client.get("/api/envs")
    assert resp.status_code == 200
    dev = _by_name(resp.json())["dev"]
    assert dev["identity"] is None
    assert dev["signed_in"] is True


def test_refused_role_credentials_read_as_signed_out(client, auth, identities):
    auth.states["dev"] = "signed_in"
    identities["dev"] = SignedOut("dev")
    dev = _by_name(client.get("/api/envs").json())["dev"]
    assert dev["signed_in"] is False
    assert dev["login"] == "signed_out"


def test_errors_surfaces_an_overlay_error(client, tmp_path):
    client.app.state.envs = registry(tmp_path, overlay="[env.dev\n")
    body = client.get("/api/envs").json()
    assert len(body["errors"]) == 1
    assert "environments.local.toml" in body["errors"][0]
    assert {e["name"] for e in body["envs"]} == {"local", "dev", "prod", "prof"}


def test_login_start_poll_logout_happy_path(client, auth):
    start = client.post("/api/envs/dev/login")
    assert start.status_code == 200
    assert start.json() == {"verification_uri_complete": "https://device.sso/?user_code=ABCD",
                            "user_code": "ABCD", "expires_in": 600, "interval": 5}
    assert client.get("/api/envs/dev/login").json() == {"state": "pending"}
    assert client.get("/api/envs/dev/login").json() == {"state": "signed_in"}
    out = client.post("/api/envs/dev/logout")
    assert out.status_code == 200
    assert out.json() == {"state": "signed_out"}
    assert ("logout", "dev") in auth.calls


def test_floci_login_409(client, auth):
    resp = client.post("/api/envs/local/login")
    assert resp.status_code == 409
    assert resp.json() == {"error": "no_login", "env": "local"}
    assert not any(c[0] == "start_login" for c in auth.calls)


def test_profile_login_409(client):
    resp = client.post("/api/envs/prof/login")
    assert resp.status_code == 409
    assert resp.json() == {"error": "profile_login",
                           "detail": "Run: aws sso login --profile my-cli-profile"}


def test_unknown_env_is_422_top_level(client):
    for method, path in [("POST", "/api/envs/nope/login"), ("GET", "/api/envs/nope/login"),
                         ("POST", "/api/envs/nope/logout")]:
        resp = client.request(method, path)
        assert resp.status_code == 422, path
        assert resp.json() == {"error": "unknown_env", "env": "nope"}


def test_not_configured_login_409(client, auth):
    resp = client.post("/api/envs/prod/login")
    assert resp.status_code == 409
    assert resp.json() == {"error": "not_configured", "env": "prod"}
    assert auth.calls == []


def test_poll_without_pending_reports_state(client, auth):
    assert client.get("/api/envs/dev/login").json() == {"state": "signed_out"}
    assert client.get("/api/envs/local/login").json() == {"state": "signed_in"}


def test_aws_errors_maps_credentials_and_denials():
    from archivenetwork.loader.envs import Env

    env = Env("dev", "aws", "D", "r", "b", "p", profile="x")

    def run(exc):
        with pytest.raises(envparam.ApiError) as info:
            with envparam.aws_errors(env):
                raise exc
        return info.value.status, info.value.body

    assert run(SignedOut("dev")) == (401, {"error": "signed_out", "env": "dev"})
    expired = ClientError({"Error": {"Code": "ExpiredToken", "Message": "old"}}, "Op")
    assert run(expired) == (401, {"error": "signed_out", "env": "dev"})
    denied = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no dynamodb:Scan"}},
                         "Scan")
    assert run(denied) == (403, {"error": "access_denied", "detail": "no dynamodb:Scan"})
    status, body = run(ClientError({"Error": {"Code": "AccessDenied", "Message": "no s3"}}, "Put"))
    assert (status, body["error"]) == (403, "access_denied")
    status, body = run(SignedOut("dev"))
    with pytest.raises(envparam.ApiError) as info:
        with envparam.aws_errors(env, during_publish=True):
            raise expired
    assert info.value.body["detail"] == envparam.EXPIRED_DURING_PUBLISH
    # Anything else is not a credential problem and passes through untouched.
    other = ClientError({"Error": {"Code": "InternalError", "Message": "x"}}, "Op")
    with pytest.raises(ClientError):
        with envparam.aws_errors(env):
            raise other
