import boto3
import pytest
from moto import mock_aws

from archivenetwork.loader.storage import S3Storage

REGION = "ap-southeast-1"
BUCKET = "test-bucket"


@pytest.fixture(autouse=True)
def _aws_creds(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


def _make_bucket():
    client = boto3.client("s3", region_name=REGION)
    client.create_bucket(
        Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION}
    )
    return client


@mock_aws
def test_key_for_is_canonical():
    s = S3Storage(BUCKET, REGION)
    assert (
        s.key_for("123", "ARCHEVT", "animusika-2026", ".jpg")
        == "fb-exports/archevt/animusika-2026/123.jpg"
    )


@mock_aws
def test_put_uploads_with_content_type(tmp_path):
    _make_bucket()
    src = tmp_path / "p.jpg"
    src.write_bytes(b"JPEGDATA")
    s = S3Storage(BUCKET, REGION)
    key = s.key_for("123", "ARCHEVT", "grp", ".jpg")
    assert s.put(src, key) is True
    head = boto3.client("s3", region_name=REGION).head_object(Bucket=BUCKET, Key=key)
    assert head["ContentType"] == "image/jpeg"


@mock_aws
def test_put_skips_existing(tmp_path):
    _make_bucket()
    src = tmp_path / "p.jpg"
    src.write_bytes(b"X")
    s = S3Storage(BUCKET, REGION)
    key = s.key_for("123", None, "grp", ".jpg")
    assert s.put(src, key) is True
    assert s.put(src, key) is False


@mock_aws
def test_exists_reflects_puts(tmp_path):
    _make_bucket()
    s = S3Storage(BUCKET, REGION)
    key = s.key_for("123", None, "grp", ".jpg")
    assert s.exists(key) is False
    src = tmp_path / "p.jpg"
    src.write_bytes(b"X")
    s.put(src, key)
    assert s.exists(key) is True


@mock_aws
def test_ensure_ready_raises_for_missing_bucket():
    s = S3Storage("no-such-bucket", REGION)
    with pytest.raises(Exception):
        s.ensure_ready()
