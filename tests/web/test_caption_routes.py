"""Album caption editing: the override, its hashtag guarantee, and what reaches the build."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from archivenetwork.app import create_app


def _loaded_client(export_root: Path, tmp_path, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    return client


def _album(client: TestClient, fbid: str) -> dict:
    inv = client.get("/api/inventory").json()
    return next(a for a in inv["albums"] if a["fb_album_id"] == fbid)


def _tag_album(client: TestClient, fbid: str, raw: str) -> None:
    """Give a fixture album a raw, hashtag-bearing description, as a real export would."""
    album = next(
        a for a in client.app.state.session.inventory.albums if a.fb_album_id == fbid
    )
    album.description = raw
    album.original_description = raw


def test_caption_edit_shows_in_the_inventory(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    assert _album(client, "111")["caption_edited"] is False

    resp = client.post("/api/album/caption", json={"album_fbid": "111", "caption": "Day two."})
    assert resp.status_code == 200
    assert resp.json()["description"] == "Day two."

    album = _album(client, "111")
    assert album["description"] == "Day two."
    assert album["caption_edited"] is True


def test_caption_edit_preserves_the_canonical_hashtag(
    export_root: Path, tmp_path: Path, monkeypatch
):
    """Prose is all the UI sends; the tags come back on server-side.

    The canonical tag decides the album's storage key and its `hashtag` column downstream,
    so a volunteer fixing a typo must not be able to delete it.
    """
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    _tag_album(client, "111", "Animo Fest 2025 #ARCHEVT #Animo")

    resp = client.post("/api/album/caption", json={"album_fbid": "111", "caption": "Animo Fest."})
    assert resp.json()["hashtags"] == ["ARCHEVT", "Animo"]
    assert _album(client, "111")["hashtags"] == ["ARCHEVT", "Animo"]

    # And the *stored* caption is raw — prose plus the tag block, FB-shaped.
    stored = json.loads((tmp_path / "workspace" / "state" / "export" / "captions.json").read_text())
    assert stored["111"] == "Animo Fest.\n\n#ARCHEVT #Animo"


def test_clearing_the_prose_keeps_the_tags(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    _tag_album(client, "111", "Old blurb #ARCHEVT")

    resp = client.post("/api/album/caption", json={"album_fbid": "111", "caption": "   "})
    assert resp.json()["description"] is None
    assert resp.json()["hashtags"] == ["ARCHEVT"]
    assert resp.json()["caption_edited"] is True


def test_clearing_an_untagged_caption_is_a_reset(export_root: Path, tmp_path: Path, monkeypatch):
    """Nothing to say and no tag to keep: that is a reset, not an empty override."""
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    _tag_album(client, "222", "")
    client.post("/api/album/caption", json={"album_fbid": "222", "caption": "Something"})

    resp = client.post("/api/album/caption", json={"album_fbid": "222", "caption": ""})
    assert resp.json()["caption_edited"] is False
    assert _album(client, "222")["caption_edited"] is False
    stored = json.loads((tmp_path / "workspace" / "state" / "export" / "captions.json").read_text())
    assert "222" not in stored


def test_caption_reset_restores_the_export_caption(
    export_root: Path, tmp_path: Path, monkeypatch
):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    _tag_album(client, "111", "Original blurb #ARCHEVT")
    client.post("/api/album/caption", json={"album_fbid": "111", "caption": "Replaced"})

    resp = client.post("/api/album/caption/reset", json={"album_fbid": "111"})
    assert resp.status_code == 200
    assert resp.json()["description"] == "Original blurb"
    album = _album(client, "111")
    assert album["description"] == "Original blurb"
    assert album["caption_edited"] is False


def test_caption_survives_a_reopen(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    client.post("/api/album/caption", json={"album_fbid": "111", "caption": "Kept across sessions"})

    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    album = _album(client, "111")
    assert album["description"] == "Kept across sessions"
    assert album["caption_edited"] is True


def test_caption_404s_for_an_unknown_album(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    resp = client.post("/api/album/caption", json={"album_fbid": "nope", "caption": "hi"})
    assert resp.status_code == 404


def test_caption_rejects_an_oversized_body(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    resp = client.post("/api/album/caption", json={"album_fbid": "111", "caption": "x" * 2001})
    assert resp.status_code == 400


def test_build_writes_the_edited_caption(export_root: Path, tmp_path: Path, monkeypatch):
    """An edited caption is only real if the ETL can read it out of the ready folder."""
    monkeypatch.setattr("archivenetwork.web.routes_build.reveal_path", lambda p: None)
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    _tag_album(client, "111", "Old #ARCHEVT")
    client.post("/api/album/caption", json={"album_fbid": "111", "caption": "New blurb"})
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})

    assert client.post("/api/build").status_code == 200
    written = json.loads(
        (tmp_path / "workspace" / "ready" / "export" / "posts" / "album" / "0.json").read_text(
            encoding="utf-8"
        )
    )
    # Raw and FB-shaped: the tag block rides along so the loader still finds #ARCHEVT.
    assert written["description"] == "New blurb\n\n#ARCHEVT"


def test_build_leaves_unedited_albums_alone(export_root: Path, tmp_path: Path, monkeypatch):
    """No override, no `description` key invented — the mirror stays faithful."""
    monkeypatch.setattr("archivenetwork.web.routes_build.reveal_path", lambda p: None)
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})

    client.post("/api/build")
    written = json.loads(
        (tmp_path / "workspace" / "ready" / "export" / "posts" / "album" / "0.json").read_text(
            encoding="utf-8"
        )
    )
    assert "description" not in written


def test_build_writes_the_renamed_album_name(export_root: Path, tmp_path: Path, monkeypatch):
    """Regression: overrides are keyed by `fb_album_id` (`111`), not the JSON stem (`0`).

    The builder used to look renames up by `album_path.stem`, so a renamed FB album shipped
    under its original Facebook name. Captions ride the same lookup, so both are pinned here.
    """
    monkeypatch.setattr("archivenetwork.web.routes_build.reveal_path", lambda p: None)
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    client.post("/api/album/rename", json={"album_fbid": "111", "name": "Animo Fest 2025"})
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})

    client.post("/api/build")
    written = json.loads(
        (tmp_path / "workspace" / "ready" / "export" / "posts" / "album" / "0.json").read_text(
            encoding="utf-8"
        )
    )
    assert written["name"] == "Animo Fest 2025"
