from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_load_folder_ok(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # workspace/ is created under cwd
    client = TestClient(create_app())
    resp = client.post("/load-folder", data={"folder": str(export_root)}, follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"] == "/gallery"


def test_load_folder_invalid(tmp_path: Path):
    client = TestClient(create_app())
    resp = client.post("/load-folder", data={"folder": str(tmp_path)})
    assert resp.status_code == 200
    assert "Missing" in resp.text
