from pathlib import Path

from archivenetwork.loader.load import load
from archivenetwork.loader.storage import LocalStorage


def test_load_inserts_albums_and_media(ready_root: Path, tmp_path: Path, pg_conn):
    store = LocalStorage(tmp_path / "store")
    r = load(ready_root, "ws-1", store, pg_conn)

    assert r.albums_inserted > 0
    assert r.media_inserted > 0
    assert r.albums_updated == 0 and r.media_updated == 0
    assert r.files_stored == r.media_inserted  # one file per media row
    assert r.orphans == [] and r.errors == []

    with pg_conn.cursor() as cur:
        cur.execute("SELECT storage_path, source_workspace_id FROM media WHERE fbid = 'g01'")
        path, ws = cur.fetchone()
    assert path.startswith("media/") and path.endswith("/g01.jpg")
    assert ws == "ws-1"
    assert store.exists(path)


def test_reload_is_idempotent_and_freezes_the_key(ready_root: Path, tmp_path: Path, pg_conn):
    store = LocalStorage(tmp_path / "store")
    first = load(ready_root, "ws-1", store, pg_conn)

    with pg_conn.cursor() as cur:
        cur.execute("SELECT storage_path FROM media WHERE fbid = 'g01'")
        original_key = cur.fetchone()[0]

    # Re-load from a *different* workspace: rows update, but no file is re-stored...
    second = load(ready_root, "ws-2", store, pg_conn)

    assert second.media_inserted == 0
    assert second.media_updated == first.media_inserted
    assert second.files_stored == 0  # nothing re-uploaded
    assert second.files_skipped == first.files_stored

    with pg_conn.cursor() as cur:
        cur.execute("SELECT storage_path, source_workspace_id FROM media WHERE fbid = 'g01'")
        key, ws = cur.fetchone()
    assert key == original_key  # ...and the key is FROZEN
    assert ws == "ws-2"  # provenance still refreshes


def test_unanchored_media_has_a_null_album(ready_root: Path, tmp_path: Path, pg_conn):
    load(ready_root, "ws-1", LocalStorage(tmp_path / "store"), pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT fb_album_id FROM media WHERE fbid = 's01'")
        assert cur.fetchone()[0] is None


def test_orphan_uri_is_reported_and_never_inserted(ready_root: Path, tmp_path: Path, pg_conn):
    # Delete a file the manifests still reference.
    victim = next((ready_root / "posts" / "media").rglob("a01.jpg"))
    victim.unlink()

    r = load(ready_root, "ws-1", LocalStorage(tmp_path / "store"), pg_conn)

    assert any("a01" in o for o in r.orphans)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM media WHERE fbid = 'a01'")
        assert cur.fetchone()[0] == 0
