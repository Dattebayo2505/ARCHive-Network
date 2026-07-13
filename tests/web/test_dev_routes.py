from fastapi.testclient import TestClient

from archivenetwork.app import create_app


def test_status_reports_disabled_without_a_database_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("archivenetwork.web.routes_dev.settings.database_url", None)
    client = TestClient(create_app())

    body = client.get("/api/dev/status").json()
    assert body["enabled"] is False
    assert body["connected"] is False
    assert "ARCHIVENETWORK_DATABASE_URL" in body["reason"]


def test_mutating_dev_routes_404_without_a_database_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("archivenetwork.web.routes_dev.settings.database_url", None)
    client = TestClient(create_app())

    assert client.post("/api/dev/schema").status_code == 404
    assert client.post("/api/dev/load").status_code == 404
    assert client.get("/api/dev/rows").status_code == 404
    assert client.get("/api/dev/validate").status_code == 404
