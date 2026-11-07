"""Publish = preflight, then `load()` into the env's bucket + tables, then a run-scoped verify.

moto S3 plus the moto `ddb` fixture (one `mock_aws` context: the fixture opens it).
"""

from __future__ import annotations

import json
from pathlib import Path

import boto3
import pytest
from botocore.exceptions import ClientError

from archivenetwork.loader import dynamo
from archivenetwork.loader.envs import Env, Sso
from archivenetwork.loader.publish import publish
from archivenetwork.loader.read import read_ready
from archivenetwork.loader.storage import S3Storage

REGION = "ap-southeast-1"
BUCKET = "publish-test-bucket"
ACCOUNT = "123456789012"
IDENTITY = (f"arn:aws:sts::{ACCOUNT}:assumed-role/Curators/u", ACCOUNT)


@pytest.fixture
def env(ddb) -> Env:
    return Env("dev", "aws", "Dev", REGION, BUCKET, ddb.prefix,
               sso=Sso("https://d.awsapps.com/start", REGION, ACCOUNT, "Curators"))


@pytest.fixture
def storage(ddb) -> S3Storage:
    client = boto3.client("s3", region_name=REGION)
    client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
    return S3Storage(BUCKET, REGION, client=client)


def _keys(storage: S3Storage) -> set[str]:
    resp = storage.client.list_objects_v2(Bucket=BUCKET)
    return {o["Key"] for o in resp.get("Contents", [])}


def _media(ddb) -> dict[str, dict]:
    return {i["id"]: i for i in dynamo.scan_items(ddb, "media")}


def _checks(steps) -> dict:
    return {c.name: c for c in steps}


class FailingS3(S3Storage):
    def __init__(self, inner: S3Storage, fbid: str):
        super().__init__(inner.bucket, inner.region, client=inner.client)
        self.fbid = fbid

    def put(self, src: Path, key: str) -> bool:
        if src.stem == self.fbid:
            raise ClientError({"Error": {"Code": "InternalError", "Message": "boom"}}, "PutObject")
        return super().put(src, key)


def test_publish_uploads_then_loads_and_verifies(ready_root, ddb, env, storage):
    r = publish(ready_root, "ws-1", env, storage, ddb, IDENTITY)
    assert r.ok is True, r.as_dict()
    assert all(c.ok for c in r.preflight)
    assert all(c.ok for c in r.verify)
    assert r.publish.files_stored > 0
    stored = {m["storage_path"] for m in _media(ddb).values()}
    assert stored == _keys(storage)
    assert len(stored) == len(read_ready(ready_root).media)


def test_republish_skips_files_and_still_ok(ready_root, ddb, env, storage):
    publish(ready_root, "ws-1", env, storage, ddb, IDENTITY)
    r = publish(ready_root, "ws-1", env, storage, ddb, IDENTITY)
    assert r.ok is True
    assert r.publish.files_stored == 0
    assert r.publish.files_skipped == len(read_ready(ready_root).media)
    assert r.publish.media_inserted == 0


def test_renamed_album_keeps_frozen_key(ready_root, ddb, env, storage):
    publish(ready_root, "ws-1", env, storage, ddb, IDENTITY)
    before = _keys(storage)
    album_json = next(
        p for p in (ready_root / "posts" / "album").glob("*.json")
        if json.loads(p.read_text(encoding="utf-8")).get("name") == "HEADLINE ONE"
    )
    raw = json.loads(album_json.read_text(encoding="utf-8"))
    raw["name"] = "A WHOLE NEW NAME"
    album_json.write_text(json.dumps(raw), encoding="utf-8")
    r = publish(ready_root, "ws-1", env, storage, ddb, IDENTITY)
    assert r.ok is True
    assert r.publish.files_stored == 0
    assert _keys(storage) == before


def test_tombstoned_media_not_uploaded(ready_root, ddb, env, storage):
    ddb.client.update_item(
        TableName=ddb.name("media"), Key={"id": {"S": "g02"}},
        UpdateExpression="SET deleted_at = :d", ExpressionAttributeValues={":d": {"S": "x"}},
    )
    r = publish(ready_root, "ws-1", env, storage, ddb, IDENTITY)
    assert "media:g02" in r.publish.skipped_deleted
    assert not any(k.endswith("/g02.jpg") for k in _keys(storage))
    checks = _checks(r.verify)
    assert checks["every manifest item is accounted for"].ok
    assert r.ok is True


def test_failed_put_makes_ok_false(ready_root, ddb, env, storage):
    r = publish(ready_root, "ws-1", env, FailingS3(storage, "g03"), ddb, IDENTITY)
    assert r.ok is False
    assert r.publish.failed == ["g03"]
    assert "g03" not in _media(ddb)
    checks = _checks(r.verify)
    assert checks["every manifest item is accounted for"].ok
    assert checks["every published media item is in the table"].ok
    assert r.as_dict()["steps"]["publish"]["ok"] is False
    assert r.as_dict()["steps"]["publish"]["failed"] == ["g03"]


def test_wrong_account_fails_preflight_and_writes_nothing(ready_root, ddb, env, storage):
    r = publish(ready_root, "ws-1", env, storage, ddb, ("arn:aws:sts::999999999999:x", "999999999999"))
    assert r.ok is False
    assert r.publish is None and r.verify is None
    assert not _checks(r.preflight)["account matches environment"].ok
    assert _keys(storage) == set()
    assert _media(ddb) == {}


def test_missing_bucket_fails_preflight(ready_root, ddb, env):
    missing = S3Storage("no-such-bucket", REGION, client=boto3.client("s3", region_name=REGION))
    r = publish(ready_root, "ws-1", env, missing, ddb, IDENTITY)
    check = _checks(r.preflight)["bucket reachable"]
    assert check.ok is False and check.detail
    assert r.publish is None
    assert _media(ddb) == {}


def test_missing_tables_fails_preflight(ready_root, ddb, env, storage):
    ddb.client.delete_table(TableName=ddb.name("media"))
    r = publish(ready_root, "ws-1", env, storage, ddb, IDENTITY)
    check = _checks(r.preflight)["tables ready"]
    assert check.ok is False
    assert ddb.name("media") in check.detail
    assert r.publish is None


def test_floci_env_skips_the_account_check(ready_root, ddb, storage):
    floci = Env("local", "floci", "L", REGION, BUCKET, ddb.prefix, endpoint_url="http://x:1")
    r = publish(ready_root, "ws-1", floci, storage, ddb, ("floci", ""))
    assert "account matches environment" not in _checks(r.preflight)
    assert r.ok is True


def test_size_mismatch_is_a_warning(ready_root, ddb, env, storage):
    publish(ready_root, "ws-1", env, storage, ddb, IDENTITY)
    key = _media(ddb)["g01"]["storage_path"]
    storage.client.put_object(Bucket=BUCKET, Key=key, Body=b"x")
    r = publish(ready_root, "ws-1", env, storage, ddb, IDENTITY)
    check = _checks(r.verify)["every published media object is in the bucket"]
    assert check.ok is True
    assert "size differs" in check.detail and "g01" in check.detail
    assert r.ok is True


def test_a_missing_object_fails_verify(ready_root, ddb, env, storage):
    publish(ready_root, "ws-1", env, storage, ddb, IDENTITY)
    key = _media(ddb)["g01"]["storage_path"]
    # Simulate an object deleted out-of-band after the item was written.
    real_put = storage.put
    storage.put = lambda src, k: False if k == key else real_put(src, k)
    storage.client.delete_object(Bucket=BUCKET, Key=key)
    r = publish(ready_root, "ws-1", env, storage, ddb, IDENTITY)
    check = _checks(r.verify)["every published media object is in the bucket"]
    assert check.ok is False and "g01" in check.detail
    assert r.ok is False


def test_as_dict_shape(ready_root, ddb, env, storage):
    ok = publish(ready_root, "ws-1", env, storage, ddb, IDENTITY).as_dict()
    assert set(ok) == {"env", "kind", "identity", "bucket", "table_prefix", "workspace_id", "ok",
                       "steps"}
    assert ok["identity"] == IDENTITY[0]
    assert set(ok["steps"]) == {"preflight", "publish", "verify"}
    for step in ("preflight", "verify"):
        assert ok["steps"][step]["ok"] is True
        assert {"name", "ok", "detail"} == set(ok["steps"][step]["checks"][0])
    assert {"ok", "albums_inserted", "albums_updated", "media_inserted", "media_updated",
            "files_stored", "files_skipped", "orphans", "errors", "skipped_deleted",
            "failed"} == set(ok["steps"]["publish"])
    json.dumps(ok)

    bad = publish(ready_root, "ws-1", env, storage, ddb, ("arn:x", "999999999999")).as_dict()
    assert bad["ok"] is False
    assert bad["steps"]["publish"] is None
    assert bad["steps"]["verify"] is None
    assert bad["steps"]["preflight"]["ok"] is False
