from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_build_produces_ready_folder(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/load-folder", data={"folder": str(export_root)})
    client.post("/toggle", data={"album_fbid": "111", "photo_fbid": "a01"})

    resp = client.post("/build")
    assert resp.status_code == 200
    assert "copied" in resp.text.lower()

    ready = tmp_path / "workspace" / "ready" / "export"
    assert (ready / "posts" / "album" / "0.json").exists()
    # non-album m01 auto-kept even though never toggled
    assert (ready / "posts" / "media" / "Mobileuploads_999" / "m01.jpg").exists()
