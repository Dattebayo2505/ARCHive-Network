from pathlib import Path

from archivenetwork.loader.load import load
from archivenetwork.loader.storage import LocalStorage
from archivenetwork.loader.validate import validate


def _checks(ready_root, tmp_path, conn):
    store = LocalStorage(tmp_path / "store")
    load(ready_root, "ws-1", store, conn)
    return {c.name: c for c in validate(ready_root, store, conn)}


def test_a_clean_load_passes_every_check(ready_root: Path, tmp_path: Path, pg_conn):
    for check in _checks(ready_root, tmp_path, pg_conn).values():
        assert check.ok, f"{check.name}: {check.detail}"


def test_detects_a_missing_object_in_the_store(ready_root: Path, tmp_path: Path, pg_conn):
    store = LocalStorage(tmp_path / "store")
    load(ready_root, "ws-1", store, pg_conn)

    next(store.root.rglob("g01.jpg")).unlink()  # object vanishes from under the row

    checks = {c.name: c for c in validate(ready_root, store, pg_conn)}
    assert checks["every media.storage_path resolves in the store"].ok is False


def test_detects_a_ready_file_no_manifest_references(ready_root: Path, tmp_path: Path, pg_conn):
    """A photo copied into ready/ that no JSON points at is invisible to a manifest-driven ETL
    and would be silently dropped — the bug posts/unanchored.json now prevents.

    The stray fbid must not collide with a real one (`n01` is now legitimately manifested).
    """
    stray = ready_root / "posts" / "media" / "zz99.jpg"
    stray.write_bytes(b"\xff\xd8\xff\xdbSTRAY")

    checks = _checks(ready_root, tmp_path, pg_conn)
    check = checks["every file in ready/ is referenced by a manifest"]
    assert check.ok is False
    assert "zz99" in check.detail
