
from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_list_and_open_workspace(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})

    listing = client.get("/api/workspaces").json()
    assert listing["last_active"] == "export"
    assert listing["workspaces"][0]["id"] == "export"
    assert listing["workspaces"][0]["display_name"] == "export"

    # Drop the live session, then reopen via the registry.
    client.app.state.session = None
    resp = client.post("/api/workspaces/open", json={"id": "export"})
    assert resp.status_code == 200
    assert resp.json()["workspace_id"] == "export"
    assert client.get("/api/session").json()["loaded"] is True


def test_open_unknown_returns_404(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    resp = client.post("/api/workspaces/open", json={"id": "nope"})
    assert resp.status_code == 404


def test_open_missing_root_returns_410(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    # Simulate the export folder being moved/deleted out-of-band.
    import shutil
    shutil.rmtree(export_root)
    resp = client.post("/api/workspaces/open", json={"id": "export"})
    assert resp.status_code == 410


def test_remove_managed_deletes_files_and_state(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Managed workspace: copy the export under workspace/imports/<id>/ so removal deletes it.
    import shutil
    imports = tmp_path / "workspace" / "imports" / "myexport"
    shutil.copytree(export_root, imports / "export")
    client = TestClient(create_app())
    # Register it as managed by ingesting from the imports tree via folder ingest is external;
    # instead open through the zip-less managed path: register directly.
    client.app.state.registry.register(imports / "export", managed=True, now=1.0)

    state_dir = tmp_path / "workspace" / "state" / "export"
    state_dir.mkdir(parents=True)
    (state_dir / "selection.json").write_text("{}", encoding="utf-8")

    resp = client.post("/api/workspaces/remove", json={"id": "export", "delete_files": True})
    assert resp.status_code == 200
    assert resp.json()["deleted_files"] is True
    assert not (imports / "export").exists()
    assert not state_dir.exists()
    assert client.app.state.registry.get("export") is None


def test_remove_external_keeps_files(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})  # external (managed=False)

    resp = client.post("/api/workspaces/remove", json={"id": "export", "delete_files": True})
    assert resp.status_code == 200
    assert resp.json()["deleted_files"] is False   # external files never deleted
    assert export_root.exists()
    assert client.app.state.registry.get("export") is None
