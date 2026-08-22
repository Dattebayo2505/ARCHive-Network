import socket

import boto3
import pytest
from botocore.exceptions import EndpointConnectionError
from moto import mock_aws

from archivenetwork.app import create_app
from archivenetwork.config import settings
from archivenetwork.inventory.parser import build_inventory
from archivenetwork.transform.builder import build_ready_folder
from archivenetwork.web import routes_s3
from fastapi.testclient import TestClient

REGION = "ap-southeast-1"
BUCKET = "test-bucket"


@pytest.fixture(autouse=True)
def _aws_creds(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


def _configure(monkeypatch, bucket=BUCKET):
    monkeypatch.setattr(settings, "s3_bucket", bucket)
    monkeypatch.setattr(settings, "s3_region", REGION)
    monkeypatch.setattr(settings, "s3_access_key_id", None)
    monkeypatch.setattr(settings, "s3_secret_access_key", None)


def _build_ready(export_root, tmp_path):
    # Build directly (NOT via /api/build, which pops the OS file manager). For a plain
    # folder import the session workspace_id == export_root.name.
    inv = build_inventory(export_root)
    keep = {p.fbid for p in inv.all_photos() if not p.is_video}
    build_ready_folder(export_root, tmp_path / "workspace" / "ready" / export_root.name, keep)


def _floci_down(monkeypatch):
    """Point floci at a port nothing is listening on, so the probe refuses instantly."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    monkeypatch.setattr(settings, "floci_endpoint_url", f"http://127.0.0.1:{port}")
    monkeypatch.setattr(settings, "floci_bucket", "archivenetwork-dev")


def test_status_reports_aws_disabled_and_floci_always_offered(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "s3_bucket", None)
    monkeypatch.setattr(settings, "s3_region", REGION)
    _floci_down(monkeypatch)
    body = TestClient(create_app()).get("/api/s3/status").json()

    assert body["aws"] == {"enabled": False}
    # Configured is not the same question as up: floci is always offered.
    assert body["floci"]["enabled"] is True
    assert body["floci"]["bucket"] == "archivenetwork-dev"
    assert body["floci"]["region"] == REGION
    assert body["floci"]["reachable"] is False
    assert body["floci"]["reason"]


def test_status_reports_both_targets_when_aws_is_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _configure(monkeypatch)
    _floci_down(monkeypatch)
    body = TestClient(create_app()).get("/api/s3/status").json()

    assert body["aws"] == {"enabled": True, "bucket": BUCKET, "region": REGION}
    assert body["floci"]["endpoint_url"].startswith("http://127.0.0.1:")
    # The AWS entry carries no liveness field — probing a remote bucket on page load
    # would be a network round trip to AWS.
    assert "reachable" not in body["aws"]


def test_upload_409_when_not_built(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _configure(monkeypatch)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    assert client.post("/api/s3/upload?target=aws").status_code == 409


@mock_aws
def test_upload_happy_path(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _configure(monkeypatch)
    boto3.client("s3", region_name=REGION).create_bucket(
        Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION}
    )
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    _build_ready(export_root, tmp_path)
    resp = client.post("/api/s3/upload?target=aws")
    assert resp.status_code == 200
    body = resp.json()
    assert body["uploaded"] > 0 and body["bucket"] == BUCKET
    assert body["target"] == "aws"
    assert body["endpoint_url"] is None
    contents = boto3.client("s3", region_name=REGION).list_objects_v2(Bucket=BUCKET).get("Contents", [])
    assert len(contents) == body["uploaded"]


@mock_aws
def test_upload_502_when_bucket_missing(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _configure(monkeypatch)
    # Bucket intentionally NOT created in moto -> head_bucket fails -> 502.
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    _build_ready(export_root, tmp_path)
    assert client.post("/api/s3/upload?target=aws").status_code == 502


def test_upload_422_when_target_is_missing(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _configure(monkeypatch)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    # A forgotten parameter must never be an implicit production write.
    assert client.post("/api/s3/upload").status_code == 422


def test_upload_404_when_aws_unconfigured_but_floci_still_allowed(
    export_root, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "s3_bucket", None)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    assert client.post("/api/s3/upload?target=aws").status_code == 404
    # Not built yet -> 409, which proves it got past the configuration gate.
    assert client.post("/api/s3/upload?target=floci").status_code == 409


def test_floci_connection_failure_names_docker(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _configure(monkeypatch)
    monkeypatch.setattr(settings, "floci_endpoint_url", "http://127.0.0.1:4566")
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    _build_ready(export_root, tmp_path)

    def _boom(*args, **kwargs):
        raise EndpointConnectionError(endpoint_url="http://127.0.0.1:4566")

    monkeypatch.setattr(routes_s3, "upload_ready", _boom)
    resp = client.post("/api/s3/upload?target=floci")
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "Docker isn't running" in detail
    assert "http://127.0.0.1:4566" in detail


def test_the_same_failure_on_aws_does_not_mention_docker(export_root, tmp_path, monkeypatch):
    # Pointing an AWS failure at Docker would be actively misleading.
    monkeypatch.chdir(tmp_path)
    _configure(monkeypatch)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    _build_ready(export_root, tmp_path)

    def _boom(*args, **kwargs):
        raise EndpointConnectionError(endpoint_url="https://s3.amazonaws.com")

    monkeypatch.setattr(routes_s3, "upload_ready", _boom)
    resp = client.post("/api/s3/upload?target=aws")
    assert resp.status_code == 502
    assert "Docker" not in resp.json()["detail"]
