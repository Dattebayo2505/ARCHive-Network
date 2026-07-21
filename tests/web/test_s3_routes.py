import boto3
import pytest
from moto import mock_aws

from archivenetwork.app import create_app
from archivenetwork.config import settings
from archivenetwork.inventory.parser import build_inventory
from archivenetwork.transform.builder import build_ready_folder
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


def test_status_disabled_when_unset(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "s3_bucket", None)
    client = TestClient(create_app())
    assert client.get("/api/s3/status").json() == {"enabled": False}


def test_status_enabled_when_set(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _configure(monkeypatch)
    client = TestClient(create_app())
    assert client.get("/api/s3/status").json() == {
        "enabled": True,
        "bucket": BUCKET,
        "region": REGION,
    }


def test_upload_404_when_unconfigured(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "s3_bucket", None)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    assert client.post("/api/s3/upload").status_code == 404


def test_upload_409_when_not_built(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _configure(monkeypatch)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    assert client.post("/api/s3/upload").status_code == 409


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
    resp = client.post("/api/s3/upload")
    assert resp.status_code == 200
    body = resp.json()
    assert body["uploaded"] > 0 and body["bucket"] == BUCKET
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
    assert client.post("/api/s3/upload").status_code == 502
