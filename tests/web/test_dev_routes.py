"""`/api/dev/*` on DynamoDB.

Route tests run on the moto `ddb` table by patching `routes_dev._table`. The settings endpoint
is pointed at a dead port, so a route that slipped past the patch fails loudly instead of
writing to the dev floci on :4566.
"""

import time
from pathlib import Path

import pytest
from botocore.exceptions import EndpointConnectionError
from fastapi.testclient import TestClient

from archivenetwork.app import create_app
from archivenetwork.loader import dynamo
from archivenetwork.web import routes_dev

DEAD_ENDPOINT = "http://127.0.0.1:1"  # port 1 is reserved and never listening


@pytest.fixture
def built_client(export_root: Path, tmp_path: Path, monkeypatch) -> TestClient:
    """A session with one picked photo, built to `workspace/ready/export`."""
    monkeypatch.chdir(tmp_path)
    # Without this every build opens a file-manager window.
    monkeypatch.setattr("archivenetwork.web.routes_build.reveal_path", lambda p: None)
    monkeypatch.setattr(routes_dev.settings, "media_root", tmp_path / "store")
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})
    assert client.post("/api/build").status_code == 200
    return client


@pytest.fixture
def dev_table(ddb, monkeypatch, tmp_path):
    monkeypatch.setattr(routes_dev, "_table", lambda: ddb)
    monkeypatch.setattr(routes_dev.settings, "dynamodb_table", ddb.name)
    monkeypatch.setattr(routes_dev.settings, "dynamodb_endpoint_url", DEAD_ENDPOINT)
    monkeypatch.setattr(routes_dev.settings, "media_root", tmp_path / "store")
    return ddb


@pytest.fixture
def client(dev_table, tmp_path, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app())


def _unconfigured(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(routes_dev.settings, "dynamodb_table", None)
    return TestClient(create_app())


def test_status_reports_disabled_without_a_table(tmp_path, monkeypatch):
    body = _unconfigured(monkeypatch, tmp_path).get("/api/dev/status").json()
    assert body["enabled"] is False
    assert body["endpoint_reachable"] is False
    assert body["table_exists"] is False
    assert "ARCHIVENETWORK_DYNAMODB_TABLE" in body["reason"]


def test_dev_routes_404_without_a_table(tmp_path, monkeypatch):
    c = _unconfigured(monkeypatch, tmp_path)
    assert c.get("/api/dev/table").status_code == 404
    assert c.post("/api/dev/table", json={}).status_code == 404
    assert c.delete("/api/dev/table").status_code == 404
    assert c.post("/api/dev/load").status_code == 404
    assert c.get("/api/dev/rows").status_code == 404
    assert c.get("/api/dev/validate").status_code == 404


def test_postgres_routes_are_gone(client):
    assert client.get("/api/dev/database").status_code == 404
    assert client.post("/api/dev/database").status_code == 404
    assert client.delete("/api/dev/database").status_code == 404
    assert client.post("/api/dev/schema").status_code == 404


def _real_table_at_dead_endpoint(monkeypatch):
    monkeypatch.setattr(routes_dev.settings, "dynamodb_table", "archers-network-dev-test")
    monkeypatch.setattr(routes_dev.settings, "dynamodb_endpoint_url", DEAD_ENDPOINT)


def test_status_reports_an_unreachable_endpoint_fast(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _real_table_at_dead_endpoint(monkeypatch)
    client = TestClient(create_app())

    start = time.monotonic()
    resp = client.get("/api/dev/status")
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


def test_every_table_route_502s_when_the_endpoint_is_unreachable(built_client, monkeypatch):
    _real_table_at_dead_endpoint(monkeypatch)
    for method, path in [
        ("POST", "/api/dev/table"),
        ("DELETE", "/api/dev/table"),
        ("POST", "/api/dev/load"),
        ("GET", "/api/dev/rows"),
        ("GET", "/api/dev/validate"),
    ]:
        resp = built_client.request(method, path)
        assert resp.status_code == 502, (method, path, resp.text)
        assert "127.0.0.1:1" in resp.json()["detail"], (method, path)


def _scan_dies(*a, **kw):
    raise EndpointConnectionError(endpoint_url=DEAD_ENDPOINT)


def test_rows_and_validate_502_when_a_scan_fails(dev_table, built_client, monkeypatch):
    """floci stopped mid-session: the probe passed, then the scan itself failed."""
    monkeypatch.setattr(dynamo, "scan_items", _scan_dies)
    for path in ("/api/dev/rows", "/api/dev/validate"):
        resp = built_client.get(path)
        assert resp.status_code == 502, (path, resp.text)
        assert "DynamoDB request failed" in resp.json()["detail"]


def test_load_502s_and_promises_a_safe_rerun(dev_table, built_client, monkeypatch):
    monkeypatch.setattr(dynamo, "prefetch", _scan_dies)
    resp = built_client.post("/api/dev/load")
    assert resp.status_code == 502
    assert "Re-running the load is safe." in resp.json()["detail"]


def test_status_survives_a_failing_count(client, monkeypatch):
    monkeypatch.setattr(dynamo, "counts", _scan_dies)
    resp = client.get("/api/dev/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"] == {}
    assert body["reason"]


def test_a_refusal_is_not_reported_as_a_missing_table(dev_table, built_client, monkeypatch):
    refused = dynamo.Probe(
        "AWS (ap-southeast-1)", True, dev_table.name, False, refused=True,
        reason="AccessDeniedException: no",
    )
    monkeypatch.setattr(dynamo, "probe", lambda t: refused)
    resp = built_client.post("/api/dev/load")
    assert resp.status_code == 502
    assert "refused" in resp.json()["detail"]


def test_table_admin_409s_on_real_aws(dev_table, client, monkeypatch):
    aws = dynamo.Table(dev_table.client, dev_table.name, on_emulator=False)
    monkeypatch.setattr(routes_dev, "_table", lambda: aws)
    for resp in (
        client.post("/api/dev/table", json={}),
        client.post("/api/dev/table", json={"reset": True}),
        client.delete("/api/dev/table"),
    ):
        assert resp.status_code == 409, resp.text
        assert "Terraform" in resp.json()["detail"]
    assert dynamo.probe(dev_table).table_exists  # nothing was dropped


def test_create_reset_delete_table(dev_table, client):
    got = client.get("/api/dev/table").json()
    assert got["table_exists"] is True
    assert got["endpoint_reachable"] is True

    created = client.post("/api/dev/table", json={}).json()
    assert created["created"] is False  # the fixture already made it
    assert created["reset"] is False

    dev_table.client.update_item(
        TableName=dev_table.name,
        Key={"PK": {"S": "MEDIA#x1"}, "SK": {"S": "#META"}},
        UpdateExpression="SET id = :i",
        ExpressionAttributeValues={":i": {"S": "x1"}},
    )
    reset = client.post("/api/dev/table", json={"reset": True}).json()
    assert reset["reset"] is True
    assert reset["table_exists"] is True
    assert reset["counts"] == {"album": 0, "media": 0}

    deleted = client.delete("/api/dev/table").json()
    assert deleted["deleted"] is True
    assert deleted["table_exists"] is False
    assert client.delete("/api/dev/table").json()["deleted"] is False


def test_load_then_rows_then_validate(dev_table, built_client):
    loaded = built_client.post("/api/dev/load")
    assert loaded.status_code == 200, loaded.text
    body = loaded.json()
    assert body["albums_inserted"] >= 1
    assert body["media_inserted"] >= 1
    assert body["skipped_deleted"] == []
    assert body["counts"]["album"] > 0
    assert body["counts"]["media"] > 0

    albums = built_client.get("/api/dev/rows", params={"type": "album"}).json()
    assert albums["type"] == "album"
    assert albums["total"] == body["counts"]["album"]
    assert {"id", "title"} <= set(albums["rows"][0])

    media = built_client.get("/api/dev/rows").json()
    assert media["type"] == "media"
    assert media["total"] == body["counts"]["media"]

    status = built_client.get("/api/dev/status").json()
    assert status["counts"] == body["counts"]

    report = built_client.get("/api/dev/validate").json()
    assert report["ok"] is True, report["checks"]


def test_rows_clamps_limit(dev_table, client):
    assert client.get("/api/dev/rows", params={"limit": 0}).json()["limit"] == 1
    assert client.get("/api/dev/rows", params={"limit": 999}).json()["limit"] == 200


def test_load_409s_when_the_table_is_missing(dev_table, built_client):
    dynamo.delete_table(dev_table)
    resp = built_client.post("/api/dev/load")
    assert resp.status_code == 409
    assert "create it first" in resp.json()["detail"]


def test_load_404s_without_a_session(client):
    assert client.post("/api/dev/load").status_code == 404


def test_rows_rejects_an_unknown_type(client):
    assert client.get("/api/dev/rows", params={"type": "photo_album"}).status_code == 422
