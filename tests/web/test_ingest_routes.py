from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_ingest_folder_ok(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # workspace/ is created under cwd
    client = TestClient(create_app())
    resp = client.post("/api/ingest/folder", json={"folder": str(export_root)})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "errors": [], "export_name": "export"}
    assert client.get("/api/session").json() == {"loaded": True, "export_name": "export"}


def test_ingest_folder_invalid(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    resp = client.post("/api/ingest/folder", json={"folder": str(tmp_path)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["errors"]  # non-empty list of missing pieces


def test_session_empty_by_default():
    client = TestClient(create_app())
    assert client.get("/api/session").json() == {"loaded": False, "export_name": None}
