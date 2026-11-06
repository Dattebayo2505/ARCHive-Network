"""Live integration tier: the DynamoDB write rules and a full load against a pinned floci.

moto patches botocore below the socket, so it cannot prove the emulator honours
`if_not_exists`, `REMOVE`, the tombstone condition, index ordering, sparse indexes or a
`Select=COUNT` scan over the real wire. This tier starts its own container (never the dev one on
:4566) from the compose pin, never `latest`.

SKIPS CLEANLY when Docker is unreachable. Read the skip count: a skipped test is not a pass.
"""

import uuid
from contextlib import contextmanager
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


def _connect(floci_conn) -> dynamo.Tables:
    endpoint, region = floci_conn
    return dynamo.connect(f"archivenetwork-itest-{uuid.uuid4().hex[:8]}", endpoint, region)


@contextmanager
def _fresh_tables(floci_conn):
    t = _connect(floci_conn)
    dynamo.create_tables(t)
    try:
        yield t
    finally:
        dynamo.delete_tables(t)


@pytest.fixture(scope="module")
def tables(floci_conn):
    """Shared by the module: 22 admin calls with waiters per test is slow. Tests use distinct ids."""
    with _fresh_tables(floci_conn) as t:
        yield t


def _get(t, kind: str, item_id: str) -> dict:
    return t.client.get_item(
        TableName=t.name(kind), Key={"id": {"S": item_id}}, ConsistentRead=True
    ).get("Item", {})


def _cms(t, kind: str, item_id: str, expr: str, values: dict | None = None) -> None:
    kw = {"ExpressionAttributeValues": values} if values else {}
    t.client.update_item(TableName=t.name(kind), Key={"id": {"S": item_id}},
                         UpdateExpression=expr, **kw)


def _media(fbid="900001", path="fb-exports/a/first/900001.jpg", created=T1,
           album_id="111", loose_section=None, creation_at="2026-07-01T00:00:00Z",
           **refresh) -> Update:
    r = {"title": "FB title", "description": "first", "loaded_at": T1, "album_id": album_id,
         "loose_section": loose_section, "creation_at": creation_at}
    r.update(refresh)
    return Update("media", fbid, r, {"storage_path": path, "fbid": fbid, "created_at": created})


def _query(t, index: str, attr: str, value: str) -> list[str]:
    items = t.client.query(
        TableName=t.name("media"), IndexName=index, KeyConditionExpression="#k = :v",
        ExpressionAttributeNames={"#k": attr}, ExpressionAttributeValues={":v": {"S": value}},
    )["Items"]
    return [i["id"]["S"] for i in items]


def test_probe_and_table_admin_on_floci(floci_conn):
    t = _connect(floci_conn)  # its own prefix: it creates and drops everything
    p = dynamo.probe(t)
    assert p.endpoint_reachable is True and p.table_exists is False and p.refused is False
    assert p.missing == list(dynamo.KINDS)
    assert dynamo.create_tables(t) == list(dynamo.KINDS) and dynamo.create_tables(t) == []
    p = dynamo.probe(t)
    assert p.table_exists is True and p.missing == []
    assert dynamo.delete_tables(t) == list(dynamo.KINDS)
    assert dynamo.probe(t).missing == list(dynamo.KINDS) and dynamo.delete_tables(t) == []


def test_write_rules_hold_on_floci(tables):
    assert dynamo.upsert(tables, _media()) == "written"
    dynamo.upsert(tables, _media(path="fb-exports/a/RENAMED/900001.jpg",
                                 created="2099-01-01T00:00:00Z", description="second",
                                 loaded_at=T2))
    it = _get(tables, "media", "900001")
    assert it["storage_path"]["S"] == "fb-exports/a/first/900001.jpg"  # if_not_exists freeze
    assert it["created_at"]["S"] == T1 and it["description"]["S"] == "second"
    assert it["id"]["S"] == "900001"  # written by the Key, never SET

    dynamo.upsert(tables, _media(description=None))
    assert "description" not in _get(tables, "media", "900001")  # REMOVE, not NULL

    _cms(tables, "media", "900001", "SET deleted_at = :d", {":d": {"S": T2}})
    before = _get(tables, "media", "900001")
    assert dynamo.upsert(tables, _media(description="resurrect")) == "skipped_deleted"
    assert _get(tables, "media", "900001") == before


def test_overrides_survive_a_reload_on_floci(tables):
    fbid = "900010"
    dynamo.upsert(tables, _media(fbid, title="FB title v1", description="FB cap v1"))
    _cms(tables, "media", fbid, "SET overrides = if_not_exists(overrides, :e)", {":e": {"M": {}}})
    _cms(tables, "media", fbid, "SET overrides.title = :t, overrides.description = :c",
         {":t": {"S": "CMS title"}, ":c": {"S": "CMS cap"}})
    dynamo.upsert(tables, _media(fbid, title="FB title v2", description=None, loaded_at=T2))
    it = _get(tables, "media", fbid)
    ov = it["overrides"]["M"]
    assert it["title"]["S"] == "FB title v2"
    assert "description" not in it and ov["description"]["S"] == "CMS cap"
    assert ov["title"]["S"] == "CMS title"

    _cms(tables, "media", fbid, "REMOVE overrides.title")
    dynamo.upsert(tables, _media(fbid, title="FB title v3", description=None))
    it = _get(tables, "media", fbid)
    assert "title" not in it["overrides"]["M"] and it["title"]["S"] == "FB title v3"


def test_by_album_orders_an_albums_media_on_floci(tables):
    for fbid, ts in [("m2", "2026-07-02T00:00:00Z"), ("m3", "2026-07-03T00:00:00Z"),
                     ("m1", "2026-07-01T00:00:00Z")]:
        dynamo.upsert(tables, _media(fbid, album_id="order-x", creation_at=ts))
    assert _query(tables, "by-album", "album_id", "order-x") == ["m1", "m2", "m3"]


def test_sparse_indexes_on_floci(tables):
    dynamo.upsert(tables, _media("sp-photo", album_id="sparse-111"))
    dynamo.upsert(tables, _media("sp-video", album_id=None, loose_section="SPARSEEVT"))
    assert _query(tables, "by-album", "album_id", "sparse-111") == ["sp-photo"]
    assert _query(tables, "by-section", "loose_section", "SPARSEEVT") == ["sp-video"]


def test_counts_on_floci(floci_conn):
    # Own tables so the count is exact; real DynamoDB returns no Items under Select=COUNT.
    with _fresh_tables(floci_conn) as t:
        dynamo.upsert(t, _media("c1"))
        dynamo.upsert(t, _media("c2"))
        got = dynamo.counts(t)
        assert got["media"] == 2 and got["album"] == 0 and set(got) == set(dynamo.KINDS)


def test_load_twice_then_validate_on_floci(ready_root: Path, tmp_path: Path, floci_conn):
    """The only real-wire proof of a two-table `BatchGetItem`. Own tables: validate reads all."""
    store = LocalStorage(tmp_path / "store")
    with _fresh_tables(floci_conn) as t:
        first = load(ready_root, "ws-1", store, t)
        assert first.albums_updated == first.media_updated == 0
        assert first.albums_inserted > 0 and first.media_inserted > 0

        second = load(ready_root, "ws-1", store, t)
        assert second.albums_inserted == second.media_inserted == 0
        assert (second.albums_updated, second.media_updated) == (
            first.albums_inserted,
            first.media_inserted,
        )
        assert second.files_stored == 0
        for check in validate(ready_root, store, t):
            assert check.ok, f"{check.name}: {check.detail}"
