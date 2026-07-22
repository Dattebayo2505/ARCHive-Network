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
    assert client.get("/api/dev/database").status_code == 404
    assert client.post("/api/dev/database").status_code == 404
    assert client.delete("/api/dev/database").status_code == 404


def test_status_distinguishes_a_down_server_from_a_missing_database(tmp_path, monkeypatch):
    """The reason string alone can't be acted on; `server_up` is what earns a button."""
    monkeypatch.chdir(tmp_path)
    # Port 1 is reserved and never listening.
    monkeypatch.setattr(
        "archivenetwork.web.routes_dev.settings.database_url",
        "postgresql://postgres@127.0.0.1:1/archivenetwork_dev",
    )
    client = TestClient(create_app())

    body = client.get("/api/dev/status").json()
    assert body["enabled"] is True
    assert body["connected"] is False
    assert body["server_up"] is False
    assert body["database"] == "archivenetwork_dev"
    assert body["database_exists"] is False


def test_database_routes_502_when_the_server_is_unreachable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "archivenetwork.web.routes_dev.settings.database_url",
        "postgresql://postgres@127.0.0.1:1/archivenetwork_dev",
    )
    client = TestClient(create_app())

    # The read-only probe still answers — it reports the server as down rather than erroring.
    body = client.get("/api/dev/database").json()
    assert body["server_up"] is False
    assert body["reason"]

    # The mutating ones cannot proceed, and must say why rather than 500.
    assert client.post("/api/dev/database").status_code == 502
    assert client.delete("/api/dev/database").status_code == 502
