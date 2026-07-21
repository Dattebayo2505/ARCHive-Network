import boto3
import pytest
from moto import mock_aws

from archivenetwork.inventory.parser import build_inventory
from archivenetwork.loader.storage import S3Storage
from archivenetwork.loader.upload import upload_ready
from archivenetwork.transform.builder import build_ready_folder

REGION = "ap-southeast-1"
BUCKET = "test-bucket"


@pytest.fixture(autouse=True)
def _aws_creds(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


def _bucket():
    c = boto3.client("s3", region_name=REGION)
    c.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})


def _build(export_root, dest):
    inv = build_inventory(export_root)
    keep = {p.fbid for p in inv.all_photos() if not p.is_video}
    build_ready_folder(export_root, dest, keep)


@mock_aws
def test_upload_puts_media_under_canonical_keys(export_root, tmp_path):
    _bucket()
    ready = tmp_path / "ready"
    _build(export_root, ready)
    result = upload_ready(ready, S3Storage(BUCKET, REGION))
    assert result.uploaded > 0
    assert result.orphans == []
    contents = boto3.client("s3", region_name=REGION).list_objects_v2(Bucket=BUCKET).get("Contents", [])
    keys = {o["Key"] for o in contents}
    assert all(k.startswith("fb-exports/") for k in keys)
    assert len(keys) == result.uploaded


@mock_aws
def test_upload_is_idempotent(export_root, tmp_path):
    _bucket()
    ready = tmp_path / "ready"
    _build(export_root, ready)
    storage = S3Storage(BUCKET, REGION)
    first = upload_ready(ready, storage)
    second = upload_ready(ready, storage)
    assert second.uploaded == 0
    assert second.skipped == first.uploaded


@mock_aws
def test_upload_reports_orphans(export_root, tmp_path):
    _bucket()
    ready = tmp_path / "ready"
    _build(export_root, ready)
    # Delete one copied media file so its manifest uri has no backing file.
    media_files = list((ready / "posts" / "media").rglob("*.jpg"))
    assert media_files
    media_files[0].unlink()
    result = upload_ready(ready, S3Storage(BUCKET, REGION))
    assert result.orphans
