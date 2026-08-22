import boto3
import pytest
from botocore.exceptions import ClientError
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


@mock_aws
def test_endpoint_url_configures_path_style_and_timeouts():
    s = S3Storage(BUCKET, REGION, endpoint_url="http://127.0.0.1:4566")
    assert s.client.meta.endpoint_url == "http://127.0.0.1:4566"
    # Virtual-hosted style would resolve <bucket>.127.0.0.1 — a hostname that does not exist.
    assert s.client.meta.config.s3["addressing_style"] == "path"
    # Without these, a dead endpoint hangs on boto3's 60s default before the route can 502.
    assert s.client.meta.config.connect_timeout == 3
    assert s.client.meta.config.read_timeout == 10
    # botocore normalizes `retries={"max_attempts": 1}` (one *retry*) into
    # `total_max_attempts` on the client's merged config. The default carries no bound at
    # all, so the presence of this key is what proves the cap was applied.
    assert s.client.meta.config.retries["total_max_attempts"] == 2


@mock_aws
def test_without_endpoint_url_the_client_still_points_at_aws():
    s = S3Storage(BUCKET, REGION)
    assert "amazonaws.com" in s.client.meta.endpoint_url


@mock_aws
def test_region_is_retained_for_bucket_creation():
    assert S3Storage(BUCKET, REGION).region == REGION


class _FakeClient:
    """Minimal stand-in so we can choose exactly which error head_bucket raises."""

    def __init__(self, head_error=None):
        self.head_error = head_error
        self.created = []

    def head_bucket(self, Bucket):
        if self.head_error is not None:
            raise self.head_error

    def create_bucket(self, **kwargs):
        self.created.append(kwargs)


def _client_error(code):
    from botocore.exceptions import ClientError as _CE

    return _CE({"Error": {"Code": code}}, "HeadBucket")


def test_create_if_missing_creates_the_bucket_on_404():
    fake = _FakeClient(head_error=_client_error("404"))
    S3Storage(BUCKET, REGION, client=fake, create_if_missing=True).ensure_ready()
    assert fake.created == [
        {"Bucket": BUCKET, "CreateBucketConfiguration": {"LocationConstraint": REGION}}
    ]


def test_create_if_missing_omits_location_constraint_for_us_east_1():
    fake = _FakeClient(head_error=_client_error("NoSuchBucket"))
    S3Storage(BUCKET, "us-east-1", client=fake, create_if_missing=True).ensure_ready()
    # S3 rejects CreateBucketConfiguration for us-east-1.
    assert fake.created == [{"Bucket": BUCKET}]


def test_create_if_missing_reraises_a_403_instead_of_creating():
    # A permissions failure must stay diagnosable, not be retried as "bucket absent".
    fake = _FakeClient(head_error=_client_error("403"))
    s = S3Storage(BUCKET, REGION, client=fake, create_if_missing=True)
    with pytest.raises(ClientError):
        s.ensure_ready()
    assert fake.created == []


def test_without_create_if_missing_a_404_still_fails_fast():
    fake = _FakeClient(head_error=_client_error("404"))
    s = S3Storage(BUCKET, REGION, client=fake)  # the AWS default
    with pytest.raises(ClientError):
        s.ensure_ready()
    assert fake.created == []
