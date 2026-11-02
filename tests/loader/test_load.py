import json
from pathlib import Path

import pytest
from botocore.exceptions import EndpointConnectionError

from archivenetwork.inventory.hashtags import canonical_tag
from archivenetwork.loader import dynamo
from archivenetwork.loader.items import (
    ALBUM_REFRESH,
    ALBUM_SET_ONCE,
    MEDIA_REFRESH,
    MEDIA_SET_ONCE,
    RETIRED,
)
from archivenetwork.loader.load import load
from archivenetwork.loader.read import read_ready
from archivenetwork.loader.storage import LocalStorage, media_key
from archivenetwork.loader.validate import validate


def _items(ddb) -> dict[str, dict]:
    return {i["PK"]: i for i in dynamo.scan_items(ddb) if i["SK"] == "#META"}


def _raw(ddb, pk: str) -> dict:
    return ddb.client.get_item(
        TableName=ddb.name, Key={"PK": {"S": pk}, "SK": {"S": "#META"}}, ConsistentRead=True
    )["Item"]


def _cms(ddb, pk: str, expr: str, values: dict) -> None:
    ddb.client.update_item(TableName=ddb.name, Key={"PK": {"S": pk}, "SK": {"S": "#META"}},
                           UpdateExpression=expr, ExpressionAttributeValues=values)


def _rename_headline_one(ready_root: Path, new_name: str) -> None:
    """Rename the album in the ready folder, exactly as a rebuild with renames.json would."""
    album_json = next(
        p
        for p in (ready_root / "posts" / "album").glob("*.json")
        if json.loads(p.read_text(encoding="utf-8")).get("name") == "HEADLINE ONE"
    )
    raw = json.loads(album_json.read_text(encoding="utf-8"))
    raw["name"] = new_name
    album_json.write_text(json.dumps(raw), encoding="utf-8")


class _Recorder:
    """Wraps a boto3 client, logging every call; optionally fails the Nth update_item."""

    def __init__(self, client, fail_update_on: int | None = None):
        self._client = client
        self._fail_on = fail_update_on
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, name):
        target = getattr(self._client, name)
        if not callable(target):
            return target

        def call(*args, **kwargs):
            self.calls.append((name, kwargs))
            if name == "update_item" and self._fail_on is not None:
                if sum(1 for n, _ in self.calls if n == "update_item") == self._fail_on:
                    raise EndpointConnectionError(endpoint_url="http://127.0.0.1:4566")
            return target(*args, **kwargs)

        return call


def test_load_inserts_albums_and_media(ready_root: Path, tmp_path: Path, ddb):
    store = LocalStorage(tmp_path / "store")
    r = load(ready_root, "ws-1", store, ddb)

    assert r.albums_inserted > 0
    assert r.media_inserted > 0
    assert r.albums_updated == 0 and r.media_updated == 0
    assert r.files_stored == r.media_inserted  # one file per media item
    assert r.orphans == [] and r.errors == [] and r.skipped_deleted == []

    g01 = _items(ddb)["MEDIA#g01"]
    assert g01["storage_path"].startswith("fb-exports/") and g01["storage_path"].endswith("/g01.jpg")
    assert g01["source_workspace_id"] == "ws-1"
    assert store.exists(g01["storage_path"])
    assert dynamo.counts(ddb) == {"album": r.albums_inserted, "media": r.media_inserted}


def test_reload_is_idempotent_and_freezes_the_key(ready_root: Path, tmp_path: Path, ddb):
    store = LocalStorage(tmp_path / "store")
    first = load(ready_root, "ws-1", store, ddb)
    original_key = _items(ddb)["MEDIA#g01"]["storage_path"]

    # Re-load from a *different* workspace: items update, but no file is re-stored...
    second = load(ready_root, "ws-2", store, ddb)

    assert second.media_inserted == 0
    assert second.media_updated == first.media_inserted
    assert second.files_stored == 0  # nothing re-uploaded
    assert second.files_skipped == first.files_stored

    g01 = _items(ddb)["MEDIA#g01"]
    assert g01["storage_path"] == original_key  # ...and the key is FROZEN
    assert g01["source_workspace_id"] == "ws-2"  # provenance still refreshes


def test_reload_classifies_from_the_prefetch(ready_root: Path, tmp_path: Path, ddb):
    store = LocalStorage(tmp_path / "store")
    first = load(ready_root, "ws-1", store, ddb)
    second = load(ready_root, "ws-1", store, ddb)
    assert second.albums_inserted == second.media_inserted == 0
    assert (second.albums_updated, second.media_updated) == (
        first.albums_inserted,
        first.media_inserted,
    )


def test_unanchored_media_has_a_null_album(
    legacy_unanchored_ready_root: Path, tmp_path: Path, ddb
):
    """Only a *pre-existing* build can carry unanchored media — new ones disregard it."""
    load(legacy_unanchored_ready_root, "ws-1", LocalStorage(tmp_path / "store"), ddb)
    s01 = _items(ddb)["MEDIA#s01"]
    assert "album_id" not in s01  # absent, never NULL
    assert s01["GSI1PK"] == "LOOSE#uncategorized"


def test_storage_key_is_grouped_by_hashtag_and_album(ready_root: Path, tmp_path: Path, ddb):
    store = LocalStorage(tmp_path / "store")
    load(ready_root, "ws-1", store, ddb)

    items = _items(ddb)
    path = items["MEDIA#g01"]["storage_path"]
    assert path == "fb-exports/archevt/headline-one/g01.jpg"
    assert canonical_tag(items["ALBUM#g01"]["hashtags"]) == "ARCHEVT"
    assert store.exists(path)


def test_untagged_unanchored_media_lands_in_uncategorized(
    legacy_unanchored_ready_root: Path, tmp_path: Path, ddb
):
    load(legacy_unanchored_ready_root, "ws-1", LocalStorage(tmp_path / "store"), ddb)
    s01 = _items(ddb)["MEDIA#s01"]
    assert s01["storage_path"] == "fb-exports/uncategorized/unanchored/s01.jpg"


def test_album_hashtag_is_persisted(ready_root: Path, tmp_path: Path, ddb):
    load(ready_root, "ws-1", LocalStorage(tmp_path / "store"), ddb)
    (album,) = [a for a in dynamo.scan_items(ddb, "album") if a["title"] == "HEADLINE TWO"]
    assert canonical_tag(album["hashtags"]) == "ARCHSPORTS"


def test_the_key_is_frozen_even_when_the_album_is_renamed(
    ready_root: Path, tmp_path: Path, ddb
):
    """A rename must never re-key an already-stored object — it would strand it.

    This is the regression test for the one risk the hashtag-grouped key introduces.
    """
    store = LocalStorage(tmp_path / "store")
    load(ready_root, "ws-1", store, ddb)
    original_key = _items(ddb)["MEDIA#g01"]["storage_path"]

    _rename_headline_one(ready_root, "Something Else Entirely")
    load(ready_root, "ws-2", store, ddb)

    key = _items(ddb)["MEDIA#g01"]["storage_path"]
    assert key == original_key  # FROZEN — not re-keyed to .../something-else-entirely/
    assert store.exists(key)


def test_orphan_uri_is_reported_and_never_inserted(ready_root: Path, tmp_path: Path, ddb):
    # Delete a file the manifests still reference.
    victim = next((ready_root / "posts" / "media").rglob("a01.jpg"))
    victim.unlink()

    r = load(ready_root, "ws-1", LocalStorage(tmp_path / "store"), ddb)

    assert any("a01" in o for o in r.orphans)
    assert "MEDIA#a01" not in _items(ddb)


def test_cms_edit_survives_a_rename_and_reload(ready_root: Path, tmp_path: Path, ddb):
    """Spec §8 regression: load, CMS edit, rename + reload, and every CMS attribute is intact."""
    store = LocalStorage(tmp_path / "store")
    load(ready_root, "ws-1", store, ddb)
    _cms(ddb, "MEDIA#g01",
         "SET is_featured = :f, GSI3PK = :g3, GSI3SK = :g3s, updated_by = :b, "
         "category_id = :c, overrides = :o",
         {":f": {"BOOL": True}, ":g3": {"S": "FEATURED"}, ":g3s": {"S": "2023-11-14T22:13:20Z"},
          ":b": {"S": "editor-1"}, ":c": {"S": "cat-1"},
          ":o": {"M": {"title": {"S": "CMS"}, "description": {"S": "CMS text"}}}})
    _cms(ddb, "ALBUM#g01", "SET overrides = :o",
         {":o": {"M": {"title": {"S": "CMS album"}, "description": {"S": "CMS album text"}}}})
    cms_keys = ("is_featured", "GSI3PK", "GSI3SK", "updated_by", "category_id", "overrides")
    media_before = _raw(ddb, "MEDIA#g01")
    album_before = _raw(ddb, "ALBUM#g01")

    _rename_headline_one(ready_root, "Something Else Entirely")
    load(ready_root, "ws-2", store, ddb)

    media_after = _raw(ddb, "MEDIA#g01")
    album_after = _raw(ddb, "ALBUM#g01")
    for k in cms_keys:
        assert media_after[k] == media_before[k], k
    assert album_after["title"] == {"S": "Something Else Entirely"}
    assert album_after["overrides"] == album_before["overrides"]
    assert media_after["storage_path"] == media_before["storage_path"]


def test_tombstoned_media_is_skipped_without_reuploading_bytes(
    ready_root: Path, tmp_path: Path, ddb
):
    store = LocalStorage(tmp_path / "store")
    load(ready_root, "ws-1", store, ddb)
    key = _items(ddb)["MEDIA#g01"]["storage_path"]
    _cms(ddb, "MEDIA#g01", "SET deleted_at = :d", {":d": {"S": "2026-11-03T00:00:00Z"}})
    (store.root / key).unlink()  # the CMS removed the object with the item
    before = _raw(ddb, "MEDIA#g01")

    r = load(ready_root, "ws-2", store, ddb)

    assert "MEDIA#g01" in r.skipped_deleted
    assert store.exists(key) is False  # bytes NOT re-uploaded
    assert _raw(ddb, "MEDIA#g01") == before
    assert r.files_stored == 0


def test_a_tombstoned_album_is_skipped(ready_root: Path, tmp_path: Path, ddb):
    store = LocalStorage(tmp_path / "store")
    first = load(ready_root, "ws-1", store, ddb)
    _cms(ddb, "ALBUM#g01", "SET deleted_at = :d", {":d": {"S": "2026-11-03T00:00:00Z"}})
    before = _raw(ddb, "ALBUM#g01")
    r = load(ready_root, "ws-2", store, ddb)
    assert r.skipped_deleted == ["ALBUM#g01"]
    assert r.albums_updated == first.albums_inserted - 1
    assert _raw(ddb, "ALBUM#g01") == before


def test_items_carry_the_new_attributes(ready_root: Path, tmp_path: Path, ddb):
    load(ready_root, "ws-1", LocalStorage(tmp_path / "store"), ddb)
    items = _items(ddb)

    g01 = items["ALBUM#g01"]
    assert g01["id"] == "g01" and g01["kind"] == "photo"
    assert g01["source"] == "fb_export_derived"
    assert g01["hashtags"] == ["ARCHEVT", "ArchersNetwork"]
    assert g01["description"] and g01["loaded_at"]
    assert items["ALBUM#111"]["source"] == "fb_export"

    m = items["MEDIA#g01"]
    assert m["id"] == m["fbid"] == "g01"
    assert m["GSI1PK"] == "ALBUM#g01" and m["GSI1SK"] == m["creation_at"]
    assert m["source_workspace_id"] == "ws-1"
    assert {"source", "description", "hashtags"}.isdisjoint(m)

    for it in items.values():
        assert RETIRED.isdisjoint(it), it["PK"]


def test_loader_only_ever_calls_update_item_with_owned_attributes(
    ready_root: Path, tmp_path: Path, ddb
):
    rec = _Recorder(ddb.client)
    table = dynamo.Table(rec, ddb.name, on_emulator=True)
    store = LocalStorage(tmp_path / "store")
    load(ready_root, "ws-1", store, table)
    load(ready_root, "ws-1", store, table)

    writes = {"put_item", "batch_write_item", "update_item", "delete_item",
              "transact_write_items"}
    called = [(n, kw) for n, kw in rec.calls if n in writes]
    assert called and {n for n, _ in called} == {"update_item"}
    owned = ALBUM_REFRESH | ALBUM_SET_ONCE | MEDIA_REFRESH | MEDIA_SET_ONCE
    for _, kw in called:
        assert kw["ReturnValues"] == "NONE"
        names = kw["ExpressionAttributeNames"]
        assert set(names.values()) <= owned | {"deleted_at"}
        (del_ph,) = [k for k, v in names.items() if v == "deleted_at"]
        assert del_ph not in kw["UpdateExpression"]
        assert del_ph in kw["ConditionExpression"]


def test_a_load_that_dies_midway_converges_on_rerun(ready_root: Path, tmp_path: Path, ddb):
    store = LocalStorage(tmp_path / "store")
    flaky = dynamo.Table(_Recorder(ddb.client, fail_update_on=3), ddb.name, on_emulator=True)
    with pytest.raises(EndpointConnectionError):
        load(ready_root, "ws-1", store, flaky)

    load(ready_root, "ws-1", store, ddb)

    data = read_ready(ready_root)
    assert dynamo.counts(ddb) == {"album": len(data.albums), "media": len(data.media)}
    items = _items(ddb)
    for row in data.media:
        expected = media_key(row.fbid, row.hashtag, row.group, Path(row.uri).suffix)
        assert items[f"MEDIA#{row.fbid}"]["storage_path"] == expected
    for check in validate(ready_root, store, ddb):
        assert check.ok, f"{check.name}: {check.detail}"
