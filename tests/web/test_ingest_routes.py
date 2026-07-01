import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def _zip_tree(src: Path, dest_zip: Path) -> None:
    """Zip `src` keeping its own folder name as the archive's top entry."""
    with zipfile.ZipFile(dest_zip, "w") as zf:
        for p in src.rglob("*"):
            zf.write(p, p.relative_to(src.parent))


def test_ingest_zip_ok(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    archive = tmp_path / "export.zip"
    _zip_tree(export_root, archive)  # archive contains export/posts/...

    client = TestClient(create_app())
    resp = client.post("/api/ingest/zip", json={"path": str(archive)})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "errors": [], "export_name": "export"}
    assert client.get("/api/session").json() == {"loaded": True, "export_name": "export"}


def test_ingest_zip_rejects_non_zip(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    not_zip = tmp_path / "notes.txt"
    not_zip.write_text("x", encoding="utf-8")

    client = TestClient(create_app())
    resp = client.post("/api/ingest/zip", json={"path": str(not_zip)})

    assert resp.status_code == 400


def test_ingest_zip_missing_path(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    resp = client.post("/api/ingest/zip", json={"path": str(tmp_path / "nope.zip")})

    assert resp.status_code == 400


def test_ingest_zip_corrupt_archive(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "broken.zip"
    bad.write_bytes(b"not really a zip")

    client = TestClient(create_app())
    resp = client.post("/api/ingest/zip", json={"path": str(bad)})

    assert resp.status_code == 400


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
