from pathlib import Path

from archivenetwork.loader.load import load
from archivenetwork.loader.storage import LocalStorage
from archivenetwork.loader.validate import validate

CHECK_NAMES = [
    "every media.storage_path resolves in the store",
    "every media.album_id names an existing album",
    "every credit and featuring edge names an existing staffer",
    "every media has a creation_at",
    "every media with an fbid is keyed by it",
    "every manifest item is in the table",
    "every file in ready/ is referenced by a manifest",
]


def _loaded(ready_root, tmp_path, ddb) -> LocalStorage:
    store = LocalStorage(tmp_path / "store")
    load(ready_root, "ws-1", store, ddb)
    return store


def _checks(ready_root, store, ddb):
    return {c.name: c for c in validate(ready_root, store, ddb)}


def _update(ddb, pk: str, expr: str, values: dict | None = None) -> None:
    kw = {"ExpressionAttributeValues": values} if values else {}
    ddb.client.update_item(TableName=ddb.name, Key={"PK": {"S": pk}, "SK": {"S": "#META"}},
                           UpdateExpression=expr, **kw)


def _put(ddb, **attrs) -> None:
    ddb.client.put_item(TableName=ddb.name, Item={k: {"S": v} for k, v in attrs.items()})


def test_a_clean_load_passes_every_check(ready_root: Path, tmp_path: Path, ddb):
    store = _loaded(ready_root, tmp_path, ddb)
    for check in _checks(ready_root, store, ddb).values():
        assert check.ok, f"{check.name}: {check.detail}"


def test_validate_reports_exactly_the_seven_checks(ready_root: Path, tmp_path: Path, ddb):
    store = _loaded(ready_root, tmp_path, ddb)
    assert [c.name for c in validate(ready_root, store, ddb)] == CHECK_NAMES


def test_detects_a_missing_object_in_the_store(ready_root: Path, tmp_path: Path, ddb):
    store = _loaded(ready_root, tmp_path, ddb)
    next(store.root.rglob("g01.jpg")).unlink()  # object vanishes from under the item

    check = _checks(ready_root, store, ddb)["every media.storage_path resolves in the store"]
    assert check.ok is False and "g01" in check.detail


def test_detects_a_ready_file_no_manifest_references(ready_root: Path, tmp_path: Path, ddb):
    """A photo copied into ready/ that no JSON points at is invisible to a manifest-driven ETL
    and would be silently dropped — the bug posts/unanchored.json now prevents.

    The stray fbid must not collide with a real one (`n01` is now legitimately manifested).
    """
    stray = ready_root / "posts" / "media" / "zz99.jpg"
    stray.write_bytes(b"\xff\xd8\xff\xdbSTRAY")

    store = _loaded(ready_root, tmp_path, ddb)
    check = _checks(ready_root, store, ddb)["every file in ready/ is referenced by a manifest"]
    assert check.ok is False
    assert "zz99" in check.detail


def test_detects_a_dangling_album_id(ready_root: Path, tmp_path: Path, ddb):
    store = _loaded(ready_root, tmp_path, ddb)
    _update(ddb, "MEDIA#g01", "SET album_id = :a", {":a": {"S": "nope"}})
    check = _checks(ready_root, store, ddb)["every media.album_id names an existing album"]
    assert check.ok is False and "g01" in check.detail


def test_detects_an_edge_to_a_missing_staffer(ready_root: Path, tmp_path: Path, ddb):
    store = _loaded(ready_root, tmp_path, ddb)
    _put(ddb, PK="MEDIA#g01", SK="CREDIT#s1", staffer_id="s1")
    check = _checks(ready_root, store, ddb)[
        "every credit and featuring edge names an existing staffer"
    ]
    assert check.ok is False and "s1" in check.detail


def test_an_edge_to_an_existing_staffer_passes(ready_root: Path, tmp_path: Path, ddb):
    store = _loaded(ready_root, tmp_path, ddb)
    _put(ddb, PK="STAFFER#s1", SK="#META", id="s1")
    _put(ddb, PK="MEDIA#g01", SK="CREDIT#s1", staffer_id="s1")
    _put(ddb, PK="ALBUM#g01", SK="FEAT#s1", staffer_id="s1")
    for check in _checks(ready_root, store, ddb).values():
        assert check.ok, f"{check.name}: {check.detail}"


def test_detects_media_without_storage_path(ready_root: Path, tmp_path: Path, ddb):
    store = _loaded(ready_root, tmp_path, ddb)
    _update(ddb, "MEDIA#g01", "REMOVE storage_path")
    check = _checks(ready_root, store, ddb)["every media.storage_path resolves in the store"]
    assert check.ok is False and "g01" in check.detail


def test_detects_media_without_creation_at(ready_root: Path, tmp_path: Path, ddb):
    store = _loaded(ready_root, tmp_path, ddb)
    _update(ddb, "MEDIA#g01", "REMOVE creation_at")
    check = _checks(ready_root, store, ddb)["every media has a creation_at"]
    assert check.ok is False and "g01" in check.detail


def test_cms_made_media_does_not_break_reconciliation(ready_root: Path, tmp_path: Path, ddb):
    store = _loaded(ready_root, tmp_path, ddb)
    key = "cms/media/01J9ZZZZZZZZZZZZZZZZZZZZZZ.jpg"
    (store.root / key).parent.mkdir(parents=True)
    (store.root / key).write_bytes(b"\xff\xd8CMS")
    _put(ddb, PK="MEDIA#01J9ZZZZZZZZZZZZZZZZZZZZZZ", SK="#META", id="01J9ZZZZZZZZZZZZZZZZZZZZZZ",
         storage_path=key, creation_at="2026-11-01T00:00:00Z")
    checks = _checks(ready_root, store, ddb)
    assert checks["every media with an fbid is keyed by it"].ok
    assert checks["every manifest item is in the table"].ok


def test_cms_made_media_outside_cms_prefix_fails(ready_root: Path, tmp_path: Path, ddb):
    store = _loaded(ready_root, tmp_path, ddb)
    key = "fb-exports/x/y/01JA.jpg"
    (store.root / key).parent.mkdir(parents=True)
    (store.root / key).write_bytes(b"\xff\xd8CMS")
    _put(ddb, PK="MEDIA#01JA", SK="#META", id="01JA", storage_path=key,
         creation_at="2026-11-01T00:00:00Z")
    check = _checks(ready_root, store, ddb)["every media with an fbid is keyed by it"]
    assert check.ok is False and "01JA" in check.detail


def test_detects_media_keyed_off_its_fbid(ready_root: Path, tmp_path: Path, ddb):
    store = _loaded(ready_root, tmp_path, ddb)
    _update(ddb, "MEDIA#g01", "SET fbid = :f", {":f": {"S": "other"}})
    check = _checks(ready_root, store, ddb)["every media with an fbid is keyed by it"]
    assert check.ok is False and "g01" in check.detail


def test_a_second_workspace_load_still_validates(ready_root: Path, tmp_path: Path, ddb):
    store = LocalStorage(tmp_path / "store")
    key = "fb-exports/archevt/last-week/old1.jpg"
    (store.root / key).parent.mkdir(parents=True)
    (store.root / key).write_bytes(b"\xff\xd8OLD")
    _put(ddb, PK="MEDIA#old1", SK="#META", id="old1", fbid="old1", storage_path=key,
         creation_at="2026-10-26T00:00:00Z")

    load(ready_root, "ws-1", store, ddb)
    checks = _checks(ready_root, store, ddb)
    for check in checks.values():
        assert check.ok, f"{check.name}: {check.detail}"
    assert "others_in_table=1" in checks["every manifest item is in the table"].detail


def test_a_tombstoned_item_whose_object_is_gone_passes(ready_root: Path, tmp_path: Path, ddb):
    store = _loaded(ready_root, tmp_path, ddb)
    _update(ddb, "MEDIA#g01", "SET deleted_at = :d", {":d": {"S": "2026-11-03T00:00:00Z"}})
    next(store.root.rglob("g01.jpg")).unlink()
    assert _checks(ready_root, store, ddb)["every media.storage_path resolves in the store"].ok


def test_detects_a_manifest_item_missing_from_the_table(ready_root: Path, tmp_path: Path, ddb):
    store = _loaded(ready_root, tmp_path, ddb)
    ddb.client.delete_item(TableName=ddb.name,
                           Key={"PK": {"S": "MEDIA#g01"}, "SK": {"S": "#META"}})
    check = _checks(ready_root, store, ddb)["every manifest item is in the table"]
    assert check.ok is False and "g01" in check.detail
