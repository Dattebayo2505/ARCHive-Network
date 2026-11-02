"""Live integration tier: the DynamoDB write rules and a full load against a pinned floci.

moto patches botocore below the socket, so it cannot prove the emulator honours
`if_not_exists`, `REMOVE`, the tombstone condition or GSI ordering over the real wire. This tier
starts its own container (never the dev one on :4566) from the compose pin, never `latest`.

SKIPS CLEANLY when Docker is unreachable. Read the skip count: a skipped test is not a pass.
"""

import uuid
from pathlib import Path

import pytest
from conftest import floci_image

from archivenetwork.loader import dynamo
from archivenetwork.loader.items import Update
from archivenetwork.loader.load import load
from archivenetwork.loader.storage import LocalStorage
from archivenetwork.loader.validate import validate

floci = pytest.importorskip("floci", reason="testcontainers-floci is not installed")

T1 = "2026-11-02T03:04:05Z"
T2 = "2026-11-09T03:04:05Z"


@pytest.fixture(scope="module")
def floci_conn():
    image = floci_image()
    if image is None:
        pytest.skip("docker-compose.yml pins no floci tag; refusing to pull latest")
    try:
        container = floci.FlociContainer(image=image)
        container.start()
    except Exception as exc:  # daemon down, image pull failure, socket permissions…
        pytest.skip(f"floci container unavailable (is Docker running?): {exc}")
    try:
        get_region = getattr(container, "get_region", None)
        region = get_region() if get_region else "us-east-1"
        yield container.get_endpoint(), region
    finally:
        container.stop()


@pytest.fixture
def table(floci_conn):
    endpoint, region = floci_conn
    t = dynamo.connect(f"archivenetwork-itest-{uuid.uuid4().hex[:8]}", endpoint, region)
    dynamo.create_table(t)
    try:
        yield t
    finally:
        dynamo.delete_table(t)


def _get(t, pk: str) -> dict:
    return t.client.get_item(
        TableName=t.name, Key={"PK": {"S": pk}, "SK": {"S": "#META"}}, ConsistentRead=True
    ).get("Item", {})


def _cms(t, pk: str, expr: str, values: dict | None = None) -> None:
    kw = {"ExpressionAttributeValues": values} if values else {}
    t.client.update_item(TableName=t.name, Key={"PK": {"S": pk}, "SK": {"S": "#META"}},
                         UpdateExpression=expr, **kw)


def _media(pk="MEDIA#900001", path="fb-exports/a/first/900001.jpg", created=T1,
           gsi1pk="ALBUM#111", gsi1sk="2026-07-01T00:00:00Z", **refresh) -> Update:
    fbid = pk.split("#", 1)[1]
    r = {"title": "FB title", "description": "first", "loaded_at": T1,
         "GSI1PK": gsi1pk, "GSI1SK": gsi1sk}
    r.update(refresh)
    return Update(pk, r, {"id": fbid, "storage_path": path, "fbid": fbid, "created_at": created})


def test_probe_and_table_admin_on_floci(floci_conn):
    endpoint, region = floci_conn
    t = dynamo.connect(f"archivenetwork-itest-{uuid.uuid4().hex[:8]}", endpoint, region)
    p = dynamo.probe(t)
    assert p.endpoint_reachable is True and p.table_exists is False and p.refused is False
    assert dynamo.create_table(t) is True and dynamo.create_table(t) is False
    assert dynamo.probe(t).table_exists is True
    assert dynamo.delete_table(t) is True
    assert dynamo.probe(t).table_exists is False and dynamo.delete_table(t) is False


def test_write_rules_hold_on_floci(table):
    assert dynamo.upsert(table, _media()) == "written"
    dynamo.upsert(table, _media(path="fb-exports/a/RENAMED/900001.jpg",
                                created="2099-01-01T00:00:00Z", description="second",
                                loaded_at=T2))
    it = _get(table, "MEDIA#900001")
    assert it["storage_path"]["S"] == "fb-exports/a/first/900001.jpg"  # if_not_exists freeze
    assert it["created_at"]["S"] == T1 and it["description"]["S"] == "second"

    dynamo.upsert(table, _media(description=None))
    assert "description" not in _get(table, "MEDIA#900001")  # REMOVE, not NULL

    _cms(table, "MEDIA#900001", "SET deleted_at = :d", {":d": {"S": T2}})
    before = _get(table, "MEDIA#900001")
    assert dynamo.upsert(table, _media(description="resurrect")) == "skipped_deleted"
    assert _get(table, "MEDIA#900001") == before


def test_overrides_survive_a_reload_on_floci(table):
    pk = "MEDIA#900010"
    dynamo.upsert(table, _media(pk, title="FB title v1", description="FB cap v1"))
    _cms(table, pk, "SET overrides = if_not_exists(overrides, :e)", {":e": {"M": {}}})
    _cms(table, pk, "SET overrides.title = :t, overrides.description = :c",
         {":t": {"S": "CMS title"}, ":c": {"S": "CMS cap"}})
    dynamo.upsert(table, _media(pk, title="FB title v2", description=None, loaded_at=T2))
    it = _get(table, pk)
    ov = it["overrides"]["M"]
    assert it["title"]["S"] == "FB title v2"
    assert "description" not in it and ov["description"]["S"] == "CMS cap"
    assert ov["title"]["S"] == "CMS title"

    _cms(table, pk, "REMOVE overrides.title")
    dynamo.upsert(table, _media(pk, title="FB title v3", description=None))
    it = _get(table, pk)
    assert "title" not in it["overrides"]["M"] and it["title"]["S"] == "FB title v3"


def test_gsi1_orders_an_albums_media_on_floci(table):
    for fbid, ts in [("m2", "2026-07-02T00:00:00Z"), ("m3", "2026-07-03T00:00:00Z"),
                     ("m1", "2026-07-01T00:00:00Z")]:
        dynamo.upsert(table, _media(f"MEDIA#{fbid}", gsi1pk="ALBUM#x", gsi1sk=ts,
                                    creation_at=ts))
    got = table.client.query(
        TableName=table.name, IndexName="GSI1", KeyConditionExpression="GSI1PK = :p",
        ExpressionAttributeValues={":p": {"S": "ALBUM#x"}},
    )["Items"]
    assert [i["PK"]["S"] for i in got] == ["MEDIA#m1", "MEDIA#m2", "MEDIA#m3"]


def test_load_twice_then_validate_on_floci(ready_root: Path, tmp_path: Path, table):
    store = LocalStorage(tmp_path / "store")
    first = load(ready_root, "ws-1", store, table)
    assert first.albums_updated == first.media_updated == 0
    assert first.albums_inserted > 0 and first.media_inserted > 0

    second = load(ready_root, "ws-1", store, table)
    assert second.albums_inserted == second.media_inserted == 0
    assert (second.albums_updated, second.media_updated) == (
        first.albums_inserted,
        first.media_inserted,
    )
    assert second.files_stored == 0
    for check in validate(ready_root, store, table):
        assert check.ok, f"{check.name}: {check.detail}"
