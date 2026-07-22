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
    assert path.startswith("fb-exports/") and path.endswith("/g01.jpg")
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


def test_unanchored_media_has_a_null_album(
    legacy_unanchored_ready_root: Path, tmp_path: Path, pg_conn
):
    """Only a *pre-existing* build can carry unanchored media — new ones disregard it."""
    load(legacy_unanchored_ready_root, "ws-1", LocalStorage(tmp_path / "store"), pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT fb_album_id FROM media WHERE fbid = 's01'")
        assert cur.fetchone()[0] is None


def test_storage_key_is_grouped_by_hashtag_and_album(ready_root: Path, tmp_path: Path, pg_conn):
    store = LocalStorage(tmp_path / "store")
    load(ready_root, "ws-1", store, pg_conn)

    with pg_conn.cursor() as cur:
        cur.execute("SELECT storage_path, hashtag FROM media WHERE fbid = 'g01'")
        path, hashtag = cur.fetchone()

    assert path == "fb-exports/archevt/headline-one/g01.jpg"
    assert hashtag == "ARCHEVT"
    assert store.exists(path)


def test_untagged_unanchored_media_lands_in_uncategorized(
    legacy_unanchored_ready_root: Path, tmp_path: Path, pg_conn
):
    load(legacy_unanchored_ready_root, "ws-1", LocalStorage(tmp_path / "store"), pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT storage_path FROM media WHERE fbid = 's01'")
        assert cur.fetchone()[0] == "fb-exports/uncategorized/unanchored/s01.jpg"


def test_album_hashtag_is_persisted(ready_root: Path, tmp_path: Path, pg_conn):
    load(ready_root, "ws-1", LocalStorage(tmp_path / "store"), pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT hashtag FROM photo_album WHERE title = 'HEADLINE TWO'")
        assert cur.fetchone()[0] == "ARCHSPORTS"


def test_the_key_is_frozen_even_when_the_album_is_renamed(
    ready_root: Path, tmp_path: Path, pg_conn
):
    """A rename must never re-key an already-stored object — it would strand it.

    This is the regression test for the one risk the hashtag-grouped key introduces.
    """
    import json

    store = LocalStorage(tmp_path / "store")
    load(ready_root, "ws-1", store, pg_conn)

    with pg_conn.cursor() as cur:
        cur.execute("SELECT storage_path FROM media WHERE fbid = 'g01'")
        original_key = cur.fetchone()[0]

    # Rename the album in the ready folder, exactly as a rebuild with renames.json would.
    album_json = next(
        p
        for p in (ready_root / "posts" / "album").glob("*.json")
        if json.loads(p.read_text(encoding="utf-8")).get("name") == "HEADLINE ONE"
    )
    raw = json.loads(album_json.read_text(encoding="utf-8"))
    raw["name"] = "Something Else Entirely"
    album_json.write_text(json.dumps(raw), encoding="utf-8")

    load(ready_root, "ws-2", store, pg_conn)

    with pg_conn.cursor() as cur:
        cur.execute("SELECT storage_path FROM media WHERE fbid = 'g01'")
        key = cur.fetchone()[0]
    assert key == original_key  # FROZEN — not re-keyed to .../something-else-entirely/
    assert store.exists(key)


def test_orphan_uri_is_reported_and_never_inserted(ready_root: Path, tmp_path: Path, pg_conn):
    # Delete a file the manifests still reference.
    victim = next((ready_root / "posts" / "media").rglob("a01.jpg"))
    victim.unlink()

    r = load(ready_root, "ws-1", LocalStorage(tmp_path / "store"), pg_conn)

    assert any("a01" in o for o in r.orphans)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM media WHERE fbid = 'a01'")
        assert cur.fetchone()[0] == 0
