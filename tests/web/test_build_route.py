from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_build_produces_ready_folder(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})

    resp = client.post("/api/build")
    assert resp.status_code == 200
    body = resp.json()
    assert "copied" in body
    assert body["albums_written"] >= 1

    ready = tmp_path / "workspace" / "ready" / "export"
    assert (ready / "posts" / "album" / "0.json").exists()
    # non-album m01 auto-kept even though never toggled
    assert (ready / "posts" / "media" / "Mobileuploads_999" / "m01.jpg").exists()
