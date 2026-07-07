from pathlib import Path

from fastapi.testclient import TestClient

from archivenetwork.app import create_app


def test_browse_lists_subdirectories(export_root: Path, tmp_path: Path):
    client = TestClient(create_app())
    resp = client.get("/api/browse", params={"path": str(export_root.parent)})
    assert resp.status_code == 200
    body = resp.json()
    assert "export" in [d["name"] for d in body["dirs"]]
    assert body["parent"] == str(export_root.parent.resolve().parent)


def test_browse_flags_export(export_root: Path):
    client = TestClient(create_app())
    resp = client.get("/api/browse", params={"path": str(export_root)})
    assert resp.status_code == 200
    assert resp.json()["is_export"] is True


def test_browse_invalid_path_returns_400(tmp_path: Path):
    client = TestClient(create_app())
    resp = client.get("/api/browse", params={"path": str(tmp_path / "missing")})
    assert resp.status_code == 400
