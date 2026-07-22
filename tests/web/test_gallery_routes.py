import json
from pathlib import Path

from fastapi.testclient import TestClient

from archivenetwork.app import create_app


def _loaded_client(export_root: Path, tmp_path, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    return client


def test_inventory_lists_albums(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    resp = client.get("/api/inventory")
    assert resp.status_code == 200
    body = resp.json()
    names = [a["name"] for a in body["albums"]]
    assert "Animo Fest" in names
    assert "Café Night" in names
    assert body["max_per_album"] == 10


def test_inventory_404_without_session(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    assert client.get("/api/inventory").status_code == 404


def test_thumbnail_served(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    resp = client.get("/api/thumb/a01")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")


def test_thumbnail_orphan_404(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    assert client.get("/api/thumb/m02").status_code == 404


def test_preview_served(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    resp = client.get("/api/preview/a01")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")


def test_preview_orphan_404(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    assert client.get("/api/preview/m02").status_code == 404


def test_reveal_photo(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    seen: list[Path] = []
    monkeypatch.setattr(
        "archivenetwork.web.routes_gallery.reveal_path", lambda p: seen.append(p)
    )
    resp = client.post("/api/reveal", json={"photo_fbid": "a01"})
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert seen[0].name == "a01.jpg"


def test_reveal_album_opens_media_folder(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    seen: list[Path] = []
    monkeypatch.setattr(
        "archivenetwork.web.routes_gallery.reveal_path", lambda p: seen.append(p)
    )
    resp = client.post("/api/reveal", json={"album_fbid": "111"})
    assert resp.status_code == 200
    assert seen[0].name == "AnimoFest_111" and seen[0].is_dir()


def test_reveal_orphan_photo_404(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    monkeypatch.setattr(
        "archivenetwork.web.routes_gallery.reveal_path", lambda p: None
    )
    assert client.post("/api/reveal", json={"photo_fbid": "m02"}).status_code == 404


def test_reveal_requires_a_target(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    assert client.post("/api/reveal", json={}).status_code == 400


def test_reveal_404_without_session(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    assert client.post("/api/reveal", json={"photo_fbid": "a01"}).status_code == 404


def test_toggle_then_cap(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    ok = client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})
    assert ok.status_code == 200
    assert ok.json() == {"selected": True, "count": 1}

    for n in range(2, 11):  # a02..a10 → reach 10
        client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": f"a{n:02d}"})
    capped = client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a11"})
    assert capped.status_code == 409
    assert capped.json()["error"] == "cap"


def test_inventory_exposes_derived_uncapped_albums(grouping_export_root, tmp_path, monkeypatch):
    client = _loaded_client(grouping_export_root, tmp_path, monkeypatch)
    body = client.get("/api/inventory").json()

    derived = [a for a in body["albums"] if a["origin"] == "Mobile uploads"]
    assert {a["name"] for a in derived} == {"HEADLINE ONE", "HEADLINE TWO"}
    # Derived caption-albums are uncapped on the wire: `None` == "no limit" to the UI.
    assert {a["name"]: a["max_per_album"] for a in derived} == {
        "HEADLINE ONE": None, "HEADLINE TWO": None
    }
    assert {p["fbid"] for p in body["archive"]} == {"t01"}

    # The `__non_album__` leftover bucket is uncapped too (the cap is moot — it is also
    # disregarded, so nothing in it is selectable at all); real FB albums stay capped.
    by_id = {a["fb_album_id"]: a for a in body["albums"]}
    assert by_id["__non_album__"]["max_per_album"] is None
    assert by_id["111"]["max_per_album"] == 1  # named FB album: min(10, 1 photo)


def test_non_album_bucket_is_marked_disregarded(grouping_export_root, tmp_path, monkeypatch):
    """The wire says which albums can never ship, and how many photos that costs.

    `disregarded` drives the UI's disabled selection affordance; `disregarded_count` is the
    number quoted in the build warning. Both come from the same place the builder subtracts
    from, so the warning cannot drift from what actually happens.
    """
    client = _loaded_client(grouping_export_root, tmp_path, monkeypatch)
    body = client.get("/api/inventory").json()

    by_id = {a["fb_album_id"]: a for a in body["albums"]}
    assert by_id["__non_album__"]["disregarded"] is True
    assert by_id["111"]["disregarded"] is False
    assert body["disregarded_count"] == len(by_id["__non_album__"]["photos"]) == 2


def test_toggling_a_non_album_photo_is_refused(grouping_export_root, tmp_path, monkeypatch):
    client = _loaded_client(grouping_export_root, tmp_path, monkeypatch)

    resp = client.post("/api/toggle", json={"album_fbid": "__non_album__", "photo_fbid": "s01"})

    # 409, but NOT "cap": there is no swap the volunteer could make to free a slot.
    assert resp.status_code == 409
    assert resp.json()["error"] == "disregarded"
    assert client.get("/api/inventory").json()["albums"]
    by_id = {a["fb_album_id"]: a for a in client.get("/api/inventory").json()["albums"]}
    assert by_id["__non_album__"]["count_selected"] == 0


def test_stale_non_album_picks_are_dropped_on_load(export_root, tmp_path, monkeypatch):
    """A selection.json written before this rule must not resurrect picks that can't ship.

    Re-opening the workspace clears them, so the counters, the gallery and the build agree
    from the first paint instead of showing checkmarks the builder silently discards.
    """
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})

    state = tmp_path / "workspace" / "state" / "export" / "selection.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"111": ["a01"], "__non_album__": ["m01"]}), encoding="utf-8")

    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    by_id = {a["fb_album_id"]: a for a in client.get("/api/inventory").json()["albums"]}

    assert by_id["111"]["count_selected"] == 1  # untouched
    assert by_id["__non_album__"]["count_selected"] == 0
    assert json.loads(state.read_text(encoding="utf-8")) == {"111": ["a01"]}


def test_archive_persists_and_restores_on_reopen(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})

    # Archive album 111 (Animo Fest).
    resp = client.post("/api/album/archive", json={"album_fbid": "111"})
    assert resp.status_code == 200

    archive_file = tmp_path / "workspace" / "state" / "export" / "archive.json"
    assert json.loads(archive_file.read_text()) == ["111"]

    # Reopen the workspace: album 111 must come back as archived, not as a normal album.
    client.app.state.session = None
    client.post("/api/workspaces/open", json={"id": "export"})
    inv = client.get("/api/inventory").json()
    assert all(a["fb_album_id"] != "111" for a in inv["albums"])
    assert any(a["fb_album_id"] == "111" for a in inv["archived_albums"])


def test_unarchive_updates_persisted_state(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    client.post("/api/album/archive", json={"album_fbid": "111"})
    client.post("/api/album/unarchive", json={"album_fbid": "111"})

    archive_file = tmp_path / "workspace" / "state" / "export" / "archive.json"
    assert json.loads(archive_file.read_text()) == []


def test_curate_picks_per_album_and_all_videos(video_export_root, tmp_path, monkeypatch):
    """Auto-curate writes real picks into the selection — it is not a return of auto-keep."""
    client = _loaded_client(video_export_root, tmp_path, monkeypatch)

    body = client.post("/api/curate", json={"per_album": 1}).json()
    assert body["per_album"] == 1
    assert body["videos_selected"] == 1  # every video is selected
    for album in body["albums"]:
        assert album["picked"] == min(1, album["available"])

    # The picks are visible in the inventory, exactly as if a human had clicked them.
    inv = client.get("/api/inventory").json()
    assert sum(a["count_selected"] for a in inv["albums"]) == body["photos_selected"]
    assert all(v["selected"] for v in inv["videos"])


def test_curate_replaces_the_previous_selection(export_root, tmp_path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a02"})

    client.post("/api/curate", json={"per_album": 1})

    inv = client.get("/api/inventory").json()
    album = next(a for a in inv["albums"] if a["fb_album_id"] == "111")
    assert album["count_selected"] == 1  # replaced, not merged
