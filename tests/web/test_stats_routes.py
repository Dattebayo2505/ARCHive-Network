from pathlib import Path

from fastapi.testclient import TestClient

from archivenetwork.app import create_app


def _loaded_client(export_root: Path, tmp_path, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    return client


def test_session_reports_stats_unseen_for_new_workspace(export_root, tmp_path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    body = client.get("/api/session").json()
    assert body["loaded"] is True
    assert body["stats_seen"] is False


def test_mark_stats_seen_persists(export_root, tmp_path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    resp = client.post("/api/stats/seen")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert client.get("/api/session").json()["stats_seen"] is True


def test_stats_seen_survives_reopen(export_root, tmp_path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    client.post("/api/stats/seen")
    # Re-ingest the same folder: same workspace id -> same state dir -> flag kept.
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    assert client.get("/api/session").json()["stats_seen"] is True


def test_mark_stats_seen_404_without_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    assert client.post("/api/stats/seen").status_code == 404
