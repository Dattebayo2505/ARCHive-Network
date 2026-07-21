from archivenetwork.config import Settings


def test_s3_defaults_are_unset_and_region_defaulted(monkeypatch):
    # Ignore any real .env / env so we assert the code defaults.
    for k in ("ARCHIVENETWORK_S3_BUCKET", "ARCHIVENETWORK_S3_ACCESS_KEY_ID",
              "ARCHIVENETWORK_S3_SECRET_ACCESS_KEY", "ARCHIVENETWORK_S3_REGION"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    assert s.s3_bucket is None
    assert s.s3_region == "ap-southeast-1"
    assert s.s3_access_key_id is None
    assert s.s3_secret_access_key is None


def test_s3_bucket_reads_env(monkeypatch):
    monkeypatch.setenv("ARCHIVENETWORK_S3_BUCKET", "my-bucket")
    s = Settings(_env_file=None)
    assert s.s3_bucket == "my-bucket"
