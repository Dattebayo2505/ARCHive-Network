from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


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
        "streamlinify.web.routes_gallery.reveal_path", lambda p: seen.append(p)
    )
    resp = client.post("/api/reveal", json={"photo_fbid": "a01"})
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert seen[0].name == "a01.jpg"


def test_reveal_album_opens_media_folder(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    seen: list[Path] = []
    monkeypatch.setattr(
        "streamlinify.web.routes_gallery.reveal_path", lambda p: seen.append(p)
    )
    resp = client.post("/api/reveal", json={"album_fbid": "111"})
    assert resp.status_code == 200
    assert seen[0].name == "AnimoFest_111" and seen[0].is_dir()


def test_reveal_orphan_photo_404(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    monkeypatch.setattr(
        "streamlinify.web.routes_gallery.reveal_path", lambda p: None
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
    assert {a["name"]: a["max_per_album"] for a in derived} == {"HEADLINE ONE": 2, "HEADLINE TWO": 3}
    assert {p["fbid"] for p in body["archive"]} == {"t01"}
