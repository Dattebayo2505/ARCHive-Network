"""`POST /api/publish?env=` — `_clients` is patched onto moto S3 + the moto `ddb` tables."""

from __future__ import annotations

from pathlib import Path

import boto3
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from fastapi.testclient import TestClient

from archivenetwork.app import create_app
from archivenetwork.loader import dynamo
from archivenetwork.loader.awsauth import SignedOut
from archivenetwork.loader.envs import load_registry
from archivenetwork.loader.storage import S3Storage
from archivenetwork.web import routes_publish

REGION = "ap-southeast-1"
BUCKET = "publish-route-bucket"
ACCOUNT = "123456789012"

ENVS = f"""
default = "local"

[env.local]
kind = "floci"
label = "Local"
endpoint_url = "http://127.0.0.1:1"
region = "{REGION}"
s3_bucket = "{BUCKET}"
table_prefix = "an-local"

[env.prod]
kind = "aws"
label = "Prod (AWS)"
region = "{REGION}"
s3_bucket = "prod-bucket"
table_prefix = "an-prod"
confirm = true
[env.prod.sso]
start_url = "https://d.awsapps.com/start"
region = "{REGION}"
account_id = "{ACCOUNT}"
role_name = "Curators"

[env.dev]
kind = "aws"
label = "Dev (AWS)"
region = "{REGION}"
s3_bucket = "dev-bucket"
table_prefix = "an-dev"
[env.dev.sso]
start_url = ""
region = "{REGION}"
account_id = ""
role_name = "Curators"
"""


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": f"{code}!"}}, "PutObject")


class CountingS3(S3Storage):
    """Raises `exc` on the Nth put."""

    def __init__(self, inner: S3Storage, nth: int | None = None, exc: Exception | None = None):
        super().__init__(inner.bucket, inner.region, client=inner.client)
        self.nth, self.exc, self.puts = nth, exc, 0

    def put(self, src: Path, key: str) -> bool:
        self.puts += 1
        if self.nth is not None and self.puts == self.nth:
            raise self.exc
        return super().put(src, key)


@pytest.fixture
def storage(ddb) -> S3Storage:
    client = boto3.client("s3", region_name=REGION)
    client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
    return S3Storage(BUCKET, REGION, client=client)


@pytest.fixture
def clients(ddb, storage, monkeypatch):
    """What `_clients` returns; tests swap `state["storage"]` or set `state["error"]`."""
    state: dict = {"storage": storage, "error": None, "asked": []}

    def fake(env, auth):
        state["asked"].append(env.name)
        if state["error"]:
            raise state["error"]
        identity = ("floci", "") if env.kind == "floci" else (
            f"arn:aws:sts::{ACCOUNT}:assumed-role/Curators/u", ACCOUNT)
        return state["storage"], ddb, identity

    monkeypatch.setattr(routes_publish, "_clients", fake)
    return state


@pytest.fixture
def app(export_root: Path, tmp_path: Path, monkeypatch, clients):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("archivenetwork.web.routes_build.reveal_path", lambda p: None)
    app = create_app()
    toml = tmp_path / "environments.toml"
    toml.write_text(ENVS, encoding="utf-8")
    app.state.envs = load_registry(toml)
    return app


@pytest.fixture
def client(app, export_root) -> TestClient:
    c = TestClient(app)
    c.post("/api/ingest/folder", json={"folder": str(export_root)})
    for n in range(1, 6):  # enough files for a failure on the 3rd put to be mid-run
        c.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": f"a{n:02d}"})
    assert c.post("/api/build").status_code == 200
    return c


def test_publish_requires_env(client):
    resp = client.post("/api/publish")
    assert resp.status_code == 422
    assert "detail" in resp.json()  # FastAPI's own validation body


def test_unknown_env_422(client):
    resp = client.post("/api/publish", params={"env": "nope"}, json={})
    assert resp.status_code == 422
    assert resp.json() == {"error": "unknown_env", "env": "nope"}


def test_publish_to_local_ok(client, ddb, storage):
    resp = client.post("/api/publish", params={"env": "local"}, json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True, body
    assert body["env"] == "local"
    assert body["kind"] == "floci"
    assert body["steps"]["publish"]["files_stored"] >= 1
    assert body["workspace_id"]
    media = dynamo.scan_items(ddb, "media")
    assert media and all(storage.exists(m["storage_path"]) for m in media)


def test_prod_requires_exact_confirm(client, clients):
    for body in ({}, {"confirm": None}, {"confirm": "Prod"}, {"confirm": " prod"},
                 {"confirm": "prod "}):
        resp = client.post("/api/publish", params={"env": "prod"}, json=body)
        assert resp.status_code == 409, body
        assert resp.json() == {"error": "confirm_required", "env": "prod"}
    assert clients["asked"] == []  # nothing reached AWS before the confirm
    resp = client.post("/api/publish", params={"env": "prod"}, json={"confirm": "prod"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["env"] == "prod"


def test_not_configured_env_409(client, clients):
    resp = client.post("/api/publish", params={"env": "dev"}, json={})
    assert resp.status_code == 409
    assert resp.json() == {"error": "not_configured", "env": "dev"}
    assert clients["asked"] == []


def test_signed_out_is_401(client, clients):
    clients["error"] = SignedOut("prod")
    resp = client.post("/api/publish", params={"env": "prod"}, json={"confirm": "prod"})
    assert resp.status_code == 401
    assert resp.json() == {"error": "signed_out", "env": "prod"}


def test_access_denied_is_403(client, clients):
    clients["error"] = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "not allowed: sts:GetCallerIdentity"}},
        "GetCallerIdentity")
    resp = client.post("/api/publish", params={"env": "prod"}, json={"confirm": "prod"})
    assert resp.status_code == 403
    assert resp.json() == {"error": "access_denied", "detail": "not allowed: sts:GetCallerIdentity"}


def test_token_expiring_mid_publish_is_one_401(client, clients, storage, ddb):
    clients["storage"] = CountingS3(storage, nth=3, exc=_client_error("ExpiredToken"))
    resp = client.post("/api/publish", params={"env": "local"}, json={})
    assert resp.status_code == 401
    body = resp.json()
    assert body == {
        "error": "signed_out",
        "env": "local",
        "detail": "Your AWS login expired during Publish. Sign in again; re-running Publish is safe.",
    }
    assert clients["storage"].puts == 3  # stopped at the first credential error
    assert dynamo.scan_items(ddb, "media") == []


def test_dynamodb_failure_mid_run_is_502(client, monkeypatch):
    def dies(*a, **kw):
        raise EndpointConnectionError(endpoint_url="http://127.0.0.1:1")

    monkeypatch.setattr(dynamo, "upsert", dies)
    resp = client.post("/api/publish", params={"env": "local"}, json={})
    assert resp.status_code == 502
    assert resp.json()["detail"].startswith("floci request failed — ")
    assert "127.0.0.1:1" in resp.json()["detail"]
    assert resp.json()["detail"].endswith("Re-running Publish is safe.")


def test_concurrent_publish_is_409(client, clients):
    lock = routes_publish._lock_for("local")
    assert lock.acquire(blocking=False)
    try:
        resp = client.post("/api/publish", params={"env": "local"}, json={})
        assert resp.status_code == 409
        assert resp.json() == {"error": "publish_running", "env": "local"}
        assert clients["asked"] == []
    finally:
        lock.release()
    assert client.post("/api/publish", params={"env": "local"}, json={}).status_code == 200


def test_lock_is_released_after_a_failure(client, clients):
    clients["error"] = SignedOut("local")
    assert client.post("/api/publish", params={"env": "local"}, json={}).status_code == 401
    assert routes_publish._lock_for("local").acquire(blocking=False)
    routes_publish._lock_for("local").release()


def test_failed_preflight_is_200_with_ok_false(client, ddb):
    ddb.client.delete_table(TableName=ddb.name("media"))
    resp = client.post("/api/publish", params={"env": "local"}, json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["steps"]["publish"] is None and body["steps"]["verify"] is None


def test_publish_without_a_session_404(app, clients):
    resp = TestClient(app).post("/api/publish", params={"env": "local"}, json={})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No export loaded"


def test_unbuilt_workspace_409(app, export_root, clients):
    c = TestClient(app)
    c.post("/api/ingest/folder", json={"folder": str(export_root)})
    resp = c.post("/api/publish", params={"env": "local"}, json={})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "This workspace has not been built yet — run Build first."
    assert clients["asked"] == []


# --- review round 1 ----------------------------------------------------------------------


@pytest.mark.parametrize("error", [
    EndpointConnectionError(endpoint_url="https://portal.sso.ap-southeast-1.amazonaws.com"),
    ClientError({"Error": {"Code": "TooManyRequestsException", "Message": "slow down"}},
                "GetRoleCredentials"),
])
def test_a_transport_failure_building_clients_is_502_not_500(client, clients, error):
    # I5: STS / SSO run while the clients are built; bad Wi-Fi gave an opaque 500.
    clients["error"] = error
    resp = client.post("/api/publish", params={"env": "prod"}, json={"confirm": "prod"})
    assert resp.status_code == 502, resp.text
    detail = resp.json()["detail"]
    assert detail.startswith("AWS request failed — ")
    assert "DynamoDB" not in detail
    assert detail.endswith("Re-running Publish is safe.")
    assert routes_publish._lock_for("prod").acquire(blocking=False)
    routes_publish._lock_for("prod").release()


def test_a_lost_connection_mid_upload_is_one_502(client, clients, storage, ddb):
    # M3: the run stops at the first lost connection instead of timing out once per file.
    clients["storage"] = CountingS3(
        storage, nth=2, exc=EndpointConnectionError(endpoint_url="http://127.0.0.1:1"))
    resp = client.post("/api/publish", params={"env": "local"}, json={})
    assert resp.status_code == 502
    assert resp.json()["detail"].startswith("floci request failed — ")
    assert clients["storage"].puts == 2
    assert dynamo.scan_items(ddb, "media") == []


def test_a_bare_403_names_the_action_and_resource(client, clients, storage):
    # M5: "AWS refused the request: Forbidden." told the volunteer nothing.
    class Refuses(S3Storage):
        def __init__(self, inner):
            super().__init__(inner.bucket, inner.region, client=inner.client)

        def put(self, src, key):
            exc = ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadObject")
            exc.resource = f"s3://{self.bucket}/{key}"
            raise exc

    clients["storage"] = Refuses(storage)
    resp = client.post("/api/publish", params={"env": "prod"}, json={"confirm": "prod"})
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert detail.startswith(f"HeadObject on s3://{BUCKET}/fb-exports/")
    assert "forbidden" in detail and "s3:ListBucket" in detail


@pytest.mark.parametrize("kw", [
    {},  # what a cross-origin `no-cors` fetch sends: no body at all
    {"content": b'{"confirm": null}', "headers": {"Content-Type": "text/plain"}},
    {"content": b"confirm=dev", "headers": {"Content-Type": "application/x-www-form-urlencoded"}},
])
def test_publish_without_a_json_body_is_415(client, clients, ddb, kw):
    # M9: a "simple" request needs no CORS preflight, so any page could have published to dev.
    resp = client.post("/api/publish", params={"env": "local"}, **kw)
    assert resp.status_code in (415, 422), resp.text
    if resp.status_code == 415:
        assert resp.json()["error"] == "json_required"
    assert clients["asked"] == []
    assert dynamo.scan_items(ddb, "media") == []


def test_a_bodiless_publish_is_exactly_415(client, clients):
    resp = client.post("/api/publish", params={"env": "local"})
    assert resp.status_code == 415
    assert resp.json() == {
        "error": "json_required",
        "detail": "Send a JSON body with Content-Type: application/json.",
    }


def test_json_with_a_charset_is_accepted(client):
    resp = client.post("/api/publish", params={"env": "local"}, content=b"{}",
                       headers={"Content-Type": "application/json; charset=utf-8"})
    assert resp.status_code == 200, resp.text


def test_clients_come_from_one_session(monkeypatch):
    # M11: `_clients` delegates to the one-session builder.
    seen = []
    monkeypatch.setattr(routes_publish.envclients, "clients_for",
                        lambda env, auth: seen.append(env) or ("s", "t", ("i", "")))
    assert routes_publish._clients("env", "auth") == ("s", "t", ("i", ""))
    assert seen == ["env"]
