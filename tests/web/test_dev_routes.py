"""`/api/dev/*`, scoped to a named environment.

Route tests run on the moto `ddb` tables and a moto bucket by patching `routes_dev._tables` /
`_storage`. The registry's floci env points at a dead port, so a route that slipped past the
patch fails loudly instead of touching the dev floci on :4566.
"""

import time
from pathlib import Path

import boto3
import pytest
from botocore.exceptions import EndpointConnectionError
from fastapi.testclient import TestClient

from archivenetwork.app import create_app
from archivenetwork.loader import dynamo
from archivenetwork.loader.awsauth import SignedOut
from archivenetwork.loader.envs import load_registry
from archivenetwork.loader.storage import S3Storage
from archivenetwork.web import routes_dev, routes_publish

DEAD_ENDPOINT = "http://127.0.0.1:1"  # port 1 is reserved and never listening
REGION = "ap-southeast-1"
BUCKET = "dev-routes-bucket"

ENVS = f"""
default = "local"

[env.local]
kind = "floci"
label = "Local"
endpoint_url = "{DEAD_ENDPOINT}"
region = "{REGION}"
s3_bucket = "{BUCKET}"
table_prefix = "an-local"

[env.dev]
kind = "aws"
label = "Dev (AWS)"
region = "{REGION}"
s3_bucket = "dev-bucket"
table_prefix = "an-dev"
[env.dev.sso]
start_url = "https://d.awsapps.com/start"
region = "{REGION}"
account_id = "123456789012"
role_name = "Curators"
"""

L = {"env": "local"}
ROUTES = [
    ("GET", "/api/dev/status"),
    ("GET", "/api/dev/tables"),
    ("POST", "/api/dev/tables"),
    ("DELETE", "/api/dev/tables"),
    ("GET", "/api/dev/rows"),
    ("GET", "/api/dev/validate"),
]


def _body(method: str) -> dict:
    """POSTs carry the JSON body the panel always sends (a bodiless one is a 415)."""
    return {"json": {}} if method == "POST" else {}


def _app(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Without this every build opens a file-manager window.
    monkeypatch.setattr("archivenetwork.web.routes_build.reveal_path", lambda p: None)
    app = create_app()
    toml = tmp_path / "environments.toml"
    toml.write_text(ENVS, encoding="utf-8")
    app.state.envs = load_registry(toml)
    return app


@pytest.fixture
def bucket(ddb) -> S3Storage:
    client = boto3.client("s3", region_name=REGION)
    client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
    return S3Storage(BUCKET, REGION, client=client)


@pytest.fixture
def dev_table(ddb, bucket, monkeypatch):
    monkeypatch.setattr(routes_dev, "_tables", lambda env, auth: ddb)
    monkeypatch.setattr(routes_dev, "_storage", lambda env, auth: bucket)
    monkeypatch.setattr(routes_publish, "_clients", lambda env, auth: (bucket, ddb, ("floci", "")))
    return ddb


@pytest.fixture
def client(dev_table, tmp_path, monkeypatch) -> TestClient:
    return TestClient(_app(tmp_path, monkeypatch))


@pytest.fixture
def built_client(export_root: Path, tmp_path: Path, monkeypatch) -> TestClient:
    """A session with one picked photo, built to `workspace/ready/export`."""
    client = TestClient(_app(tmp_path, monkeypatch))
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})
    assert client.post("/api/build").status_code == 200
    return client


def _publish(c: TestClient) -> dict:
    resp = c.post("/api/publish", params=L, json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True, resp.json()
    return resp.json()


def test_every_route_requires_an_env(client):
    for method, path in ROUTES:
        resp = client.request(method, path, **_body(method))
        assert resp.status_code == 422, (method, path)


def test_an_unknown_env_is_422(client):
    for method, path in ROUTES:
        resp = client.request(method, path, params={"env": "nope"}, **_body(method))
        assert resp.status_code == 422, (method, path)
        assert resp.json() == {"error": "unknown_env", "env": "nope"}


def test_status_is_always_enabled_and_names_the_env(client):
    body = client.get("/api/dev/status", params=L).json()
    assert body["enabled"] is True
    assert body["env"] == "local"
    assert body["kind"] == "floci"
    assert body["table_exists"] is True
    assert "media_root" not in body and "media_base_url" not in body


def test_signed_out_aws_env_is_401(tmp_path, monkeypatch):
    c = TestClient(_app(tmp_path, monkeypatch))

    class Out:
        def session(self, env):
            raise SignedOut(env.name)

    c.app.state.auth = Out()
    for method, path in ROUTES:
        resp = c.request(method, path, params={"env": "dev"}, **_body(method))
        if path == "/api/dev/validate":
            assert resp.status_code == 404  # no session: checked before any AWS call
            continue
        assert resp.status_code == 401, (method, path, resp.text)
        assert resp.json() == {"error": "signed_out", "env": "dev"}


def test_old_table_route_is_gone(client):
    assert client.get("/api/dev/table").status_code == 404
    assert client.post("/api/dev/table", json={}).status_code in (404, 405)
    assert client.delete("/api/dev/table").status_code in (404, 405)


def test_load_route_is_gone(client):
    assert client.post("/api/dev/load", params=L).status_code in (404, 405)


def test_upload_route_is_gone(client):
    assert client.post("/api/s3/upload", params={"target": "floci"}).status_code == 404
    assert client.get("/api/s3/status").status_code == 404
    assert client.get("/store/fb-exports/x.jpg").status_code == 404


def test_postgres_routes_are_gone(client):
    assert client.get("/api/dev/database").status_code == 404
    assert client.post("/api/dev/database").status_code == 404
    assert client.delete("/api/dev/database").status_code == 404
    assert client.post("/api/dev/schema").status_code == 404


def test_status_reports_an_unreachable_endpoint_fast(tmp_path, monkeypatch):
    client = TestClient(_app(tmp_path, monkeypatch))
    start = time.monotonic()
    resp = client.get("/api/dev/status", params=L)
    elapsed = time.monotonic() - start

    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["on_emulator"] is True
    assert body["endpoint_reachable"] is False
    assert body["table_exists"] is False
    assert body["counts"] == {}
    assert body["reason"]
    assert elapsed < 10


def test_every_table_route_502s_when_the_endpoint_is_unreachable(built_client):
    for method, path in ROUTES[2:]:
        resp = built_client.request(method, path, params=L, **_body(method))
        assert resp.status_code == 502, (method, path, resp.text)
        assert "127.0.0.1:1" in resp.json()["detail"], (method, path)


def _scan_dies(*a, **kw):
    raise EndpointConnectionError(endpoint_url=DEAD_ENDPOINT)


def test_rows_and_validate_502_when_a_scan_fails(dev_table, built_client, monkeypatch):
    """floci stopped mid-session: the probe passed, then the scan itself failed."""
    monkeypatch.setattr(dynamo, "scan_items", _scan_dies)
    for path in ("/api/dev/rows", "/api/dev/validate"):
        resp = built_client.get(path, params=L)
        assert resp.status_code == 502, (path, resp.text)
        assert resp.json()["detail"].startswith("floci request failed — "), path


def test_status_survives_a_failing_count(client, monkeypatch):
    monkeypatch.setattr(dynamo, "counts", _scan_dies)
    resp = client.get("/api/dev/status", params=L)
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"] == {}
    assert body["reason"]


def _refused(dev_table, reason: str) -> dynamo.Probe:
    return dynamo.Probe(
        endpoint="AWS (ap-southeast-1)",
        endpoint_reachable=True,
        prefix=dev_table.prefix,
        tables={k: dev_table.name(k) for k in dynamo.LOADER_KINDS},
        missing=[],
        table_exists=False,
        refused=True,
        reason=reason,
    )


def test_a_refusal_is_not_reported_as_a_missing_table(dev_table, built_client, monkeypatch):
    monkeypatch.setattr(dynamo, "probe", lambda t: _refused(dev_table, "InternalFailure: no"))
    resp = built_client.get("/api/dev/rows", params=L)
    assert resp.status_code == 502
    assert "refused" in resp.json()["detail"]


def test_a_denied_probe_is_403_and_an_expired_one_401(dev_table, built_client, monkeypatch):
    monkeypatch.setattr(dynamo, "probe",
                        lambda t: _refused(dev_table, "AccessDeniedException: no Describe"))
    resp = built_client.get("/api/dev/rows", params=L)
    assert resp.status_code == 403
    assert resp.json() == {"error": "access_denied", "detail": "no Describe"}
    monkeypatch.setattr(dynamo, "probe",
                        lambda t: _refused(dev_table, "ExpiredTokenException: old"))
    resp = built_client.get("/api/dev/rows", params=L)
    assert resp.status_code == 401
    assert resp.json() == {"error": "signed_out", "env": "local"}


def test_tables_admin_refused_on_aws_env(dev_table, client, monkeypatch):
    aws = dynamo.Tables(dev_table.client, dev_table.prefix, on_emulator=False)
    monkeypatch.setattr(routes_dev, "_tables", lambda env, auth: aws)
    for resp in (
        client.post("/api/dev/tables", params={"env": "dev"}, json={}),
        client.post("/api/dev/tables", params={"env": "dev"}, json={"reset": True}),
        client.delete("/api/dev/tables", params={"env": "dev"}),
    ):
        assert resp.status_code == 409, resp.text
        assert "by hand" in resp.json()["detail"]
        assert resp.json()["detail"] == routes_dev.REFUSE_AWS
    assert dynamo.probe(dev_table).table_exists  # nothing was dropped


def test_create_reset_delete_tables(dev_table, client):
    got = client.get("/api/dev/tables", params=L).json()
    assert got["table_exists"] is True and got["missing"] == []
    assert got["endpoint_reachable"] is True
    assert got["tables"]["staff_term"] == dev_table.name("staff_term")

    created = client.post("/api/dev/tables", params=L, json={}).json()
    assert created["created"] == []  # the fixture already made them
    assert created["reset"] is False

    dev_table.client.update_item(
        TableName=dev_table.name("media"),
        Key={"id": {"S": "x1"}},
        UpdateExpression="SET title = :t",
        ExpressionAttributeValues={":t": {"S": "x1"}},
    )
    reset = client.post("/api/dev/tables", params=L, json={"reset": True}).json()
    assert reset["reset"] is True
    assert reset["table_exists"] is True
    assert reset["created"] == list(dynamo.KINDS)
    assert set(reset["counts"]) == set(dynamo.KINDS)
    assert set(reset["counts"].values()) == {0}

    deleted = client.delete("/api/dev/tables", params=L).json()
    assert deleted["deleted"] == list(dynamo.KINDS)
    assert deleted["table_exists"] is False
    assert client.delete("/api/dev/tables", params=L).json()["deleted"] == []


def test_publish_then_rows_then_validate(dev_table, built_client):
    body = _publish(built_client)
    assert body["steps"]["publish"]["albums_inserted"] >= 1
    assert body["steps"]["publish"]["media_inserted"] >= 1

    status = built_client.get("/api/dev/status", params=L).json()
    assert status["counts"]["album"] > 0 and status["counts"]["media"] > 0

    albums = built_client.get("/api/dev/rows", params={**L, "type": "album"}).json()
    assert albums["type"] == "album"
    assert albums["total"] == status["counts"]["album"]
    assert {"id", "title"} <= set(albums["rows"][0])
    assert "preview_url" not in albums["rows"][0]

    media = built_client.get("/api/dev/rows", params=L).json()
    assert media["type"] == "media"
    assert media["total"] == status["counts"]["media"]

    report = built_client.get("/api/dev/validate", params=L).json()
    assert report["ok"] is True, report["checks"]


def test_rows_media_have_preview_url(dev_table, built_client, bucket):
    _publish(built_client)
    dev_table.client.update_item(  # a CMS-made item with no object yet
        TableName=dev_table.name("media"), Key={"id": {"S": "cms1"}},
        UpdateExpression="SET title = :t", ExpressionAttributeValues={":t": {"S": "cms"}},
    )
    rows = built_client.get("/api/dev/rows", params=L).json()["rows"]
    with_path = [r for r in rows if r.get("storage_path")]
    assert with_path
    for row in with_path:
        assert BUCKET in row["preview_url"]
        assert row["storage_path"] in row["preview_url"]
    assert "preview_url" not in next(r for r in rows if r["id"] == "cms1")


def test_validate_checks_the_env_bucket(dev_table, built_client, bucket):
    _publish(built_client)
    key = dynamo.scan_items(dev_table, "media")[0]["storage_path"]
    bucket.client.delete_object(Bucket=BUCKET, Key=key)
    report = built_client.get("/api/dev/validate", params=L).json()
    first = report["checks"][0]
    assert first["name"] == "every media.storage_path resolves in the store"
    assert first["ok"] is False
    assert report["ok"] is False


def test_rows_clamps_limit(dev_table, client):
    assert client.get("/api/dev/rows", params={**L, "limit": 0}).json()["limit"] == 1
    assert client.get("/api/dev/rows", params={**L, "limit": 999}).json()["limit"] == 200


def test_rows_409s_when_the_tables_are_missing(dev_table, built_client):
    dynamo.delete_tables(dev_table)
    resp = built_client.get("/api/dev/rows", params=L)
    assert resp.status_code == 409
    assert "create them first" in resp.json()["detail"]


def test_a_missing_table_is_named_and_create_fills_only_it(dev_table, built_client):
    dev_table.client.delete_table(TableName=dev_table.name("credit"))
    for path in ("/api/dev/rows", "/api/dev/validate"):
        resp = built_client.get(path, params=L)
        assert resp.status_code == 409, (path, resp.text)
        assert dev_table.name("credit") in resp.json()["detail"]
        assert dev_table.name("album") not in resp.json()["detail"]

    created = built_client.post("/api/dev/tables", params=L, json={}).json()
    assert created["created"] == ["credit"]
    assert created["table_exists"] is True
    assert built_client.get("/api/dev/rows", params=L).status_code == 200


def test_validate_404s_without_a_session(client):
    assert client.get("/api/dev/validate", params=L).status_code == 404


def test_rows_rejects_an_unknown_type(client):
    assert client.get("/api/dev/rows", params={**L, "type": "photo_album"}).status_code == 422


# --- review round 1 ----------------------------------------------------------------------


def test_a_transport_failure_building_tables_is_502_not_500(tmp_path, monkeypatch):
    # I5: STS / SSO run while `_tables` builds the client; an offline laptop gave a 500.
    def offline(env, auth):
        raise EndpointConnectionError(endpoint_url="https://portal.sso.ap-southeast-1.amazonaws.com")

    monkeypatch.setattr(routes_dev, "_tables", offline)
    c = TestClient(_app(tmp_path, monkeypatch))
    for method, path in ROUTES:
        if path == "/api/dev/validate":
            continue  # no session: a 404 before any AWS call
        resp = c.request(method, path, params={"env": "dev"}, **_body(method))
        assert resp.status_code == 502, (method, path, resp.text)
        assert resp.json()["detail"].startswith("AWS request failed — "), (method, path)
        assert resp.json()["detail"].endswith("Re-running is safe."), (method, path)


def test_status_maps_a_refused_probe_like_rows_does(dev_table, client, monkeypatch):
    # B7 / CA5: an expired login read as "check your role's permissions" on the status card.
    monkeypatch.setattr(dynamo, "probe", lambda t: _refused(dev_table, "ExpiredTokenException: old"))
    resp = client.get("/api/dev/status", params=L)
    assert resp.status_code == 401
    assert resp.json() == {"error": "signed_out", "env": "local"}

    monkeypatch.setattr(dynamo, "probe",
                        lambda t: _refused(dev_table, "AccessDeniedException: no Describe"))
    resp = client.get("/api/dev/status", params=L)
    assert resp.status_code == 403
    assert resp.json() == {"error": "access_denied", "detail": "no Describe"}

    # Anything else is still a refusal the card renders, not an error.
    monkeypatch.setattr(dynamo, "probe", lambda t: _refused(dev_table, "InternalFailure: no"))
    resp = client.get("/api/dev/status", params=L)
    assert resp.status_code == 200
    assert resp.json()["refused"] is True


def test_an_expired_profile_login_is_401_not_unreachable(dev_table, built_client, monkeypatch):
    # M6: the probe raised it as "Can't reach DynamoDB" (502) for a profile env.
    from botocore.exceptions import UnauthorizedSSOTokenError

    def expired(t):
        raise UnauthorizedSSOTokenError()

    monkeypatch.setattr(dynamo, "probe", expired)
    for method, path in ROUTES:
        resp = built_client.request(method, path, params=L, **_body(method))
        assert resp.status_code == 401, (method, path, resp.text)
        assert resp.json() == {"error": "signed_out", "env": "local"}


@pytest.mark.parametrize("kw", [
    {},
    {"content": b'{"reset": true}', "headers": {"Content-Type": "text/plain"}},
])
def test_create_tables_without_a_json_body_is_rejected(dev_table, client, kw):
    # M9: a cross-origin page could otherwise reset floci's tables with a simple request.
    dev_table.client.delete_table(TableName=dev_table.name("media"))
    resp = client.post("/api/dev/tables", params=L, **kw)
    assert resp.status_code in (415, 422), resp.text
    assert dev_table.name("media") in dynamo.probe(dev_table).tables.values()
    assert "media" in dynamo.probe(dev_table).missing  # nothing was created or reset


def test_a_bodiless_create_tables_is_exactly_415(client):
    resp = client.post("/api/dev/tables", params=L)
    assert resp.status_code == 415
    assert resp.json()["error"] == "json_required"


# --- review round 2 ----------------------------------------------------------------------


def test_an_s3_failure_in_rows_is_not_labelled_dynamodb(dev_table, built_client, monkeypatch):
    # Round 2: presign / HEADs / the SSO refresh fail inside rows and validate too.
    from botocore.exceptions import ClientError

    item = {"id": "a01", "storage_path": "fb-exports/x/y/a01.jpg"}
    monkeypatch.setattr(dynamo, "scan_items", lambda t, kind: [dict(item)])

    def refuses(key, expires=900):
        raise ClientError({"Error": {"Code": "InternalError", "Message": "S3 is sad"}},
                          "GeneratePresignedUrl")

    monkeypatch.setattr(S3Storage, "presign", lambda self, key, expires=900: refuses(key))
    resp = built_client.get("/api/dev/rows", params=L)
    assert resp.status_code == 502, resp.text
    detail = resp.json()["detail"]
    assert detail.startswith("floci request failed — ") and "S3 is sad" in detail
    assert "DynamoDB" not in detail

    monkeypatch.setattr(S3Storage, "exists", lambda self, key: refuses(key))
    resp = built_client.get("/api/dev/validate", params=L)
    assert resp.status_code == 502, resp.text
    assert resp.json()["detail"].startswith("floci request failed — ")
