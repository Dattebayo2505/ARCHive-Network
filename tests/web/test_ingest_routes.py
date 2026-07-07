import json as _json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from archivenetwork.app import create_app


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
    body = resp.json()
    assert body["ok"] is True and body["export_name"] == "export"
    assert body["workspace_id"] == "export" and body["deduped"] is False
    status = client.get("/api/session").json()
    assert status["loaded"] is True and status["display_name"] == "export"


def test_ingest_zip_names_workspace_from_zip_filename(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # The extracted root folder is "export", but the zip carries the friendly name.
    archive = tmp_path / "facebook-Test-2026-01-02-abc.zip"
    _zip_tree(export_root, archive)

    client = TestClient(create_app())
    body = client.post("/api/ingest/zip", json={"path": str(archive)}).json()

    assert body["workspace_id"] == "facebook-Test-2026-01-02-abc"
    assert body["display_name"] == "Test Facebook Export | 2026-01-02"
    assert body["export_name"] == "export"        # extracted root name is unchanged
    # State dir is keyed by the zip-derived id, not the extracted folder name.
    assert (tmp_path / "workspace" / "state" / "facebook-Test-2026-01-02-abc").is_dir()

    # Reopening by that id must resolve to the same workspace (idempotent).
    client.app.state.session = None
    reopened = client.post("/api/workspaces/open", json={"id": "facebook-Test-2026-01-02-abc"})
    assert reopened.status_code == 200
    assert reopened.json()["workspace_id"] == "facebook-Test-2026-01-02-abc"


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


def test_ingest_upload_extracts_and_removes_archive(
    export_root: Path, tmp_path: Path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    archive = tmp_path / "export.zip"
    _zip_tree(export_root, archive)  # archive contains export/posts/...

    client = TestClient(create_app())
    with archive.open("rb") as fh:
        resp = client.post("/api/ingest/upload", files={"file": ("export.zip", fh, "application/zip")})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True and body["export_name"] == "export"
    import_dir = tmp_path / "workspace" / "import"
    # The tree is extracted under workspace/imports/<stem>/…
    assert (tmp_path / "workspace" / "imports" / "export").is_dir()
    # …and the uploaded archive is not left sitting alongside it.
    assert not (import_dir / "export.zip").exists()
    assert list(import_dir.glob("*.zip")) == []


def test_ingest_folder_ok(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # workspace/ is created under cwd
    client = TestClient(create_app())
    resp = client.post("/api/ingest/folder", json={"folder": str(export_root)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True and body["export_name"] == "export"
    status = client.get("/api/session").json()
    assert status["loaded"] is True and status["display_name"] == "export"


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


def test_ingest_folder_writes_per_workspace_state(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())

    resp = client.post("/api/ingest/folder", json={"folder": str(export_root)})
    body = resp.json()

    assert body["ok"] is True
    assert body["workspace_id"] == "export"
    assert body["display_name"] == "export"          # no date -> raw name
    # Per-workspace state dir is created under workspace/state/<id>/
    state_dir = tmp_path / "workspace" / "state" / "export"
    assert state_dir.is_dir()
    # The registry file exists and records this workspace.
    reg = _json.loads((tmp_path / "workspace" / "workspaces.json").read_text())
    assert reg["last_active"] == "export"
    assert any(w["id"] == "export" for w in reg["workspaces"])


def test_two_exports_keep_separate_selection(export_root, video_export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())

    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})

    # Switch to the other export by ingesting it; first export's selection must not leak.
    client.post("/api/ingest/folder", json={"folder": str(video_export_root)})
    sel_a = tmp_path / "workspace" / "state" / "export" / "selection.json"
    sel_b = tmp_path / "workspace" / "state" / "video_export" / "selection.json"
    assert sel_a.exists()                    # first workspace kept its own file
    assert not sel_b.exists() or _json.loads(sel_b.read_text()) == {}


def test_session_status_includes_display_name(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})

    status = client.get("/api/session").json()
    assert status == {
        "loaded": True,
        "export_name": "export",
        "workspace_id": "export",
        "display_name": "export",
    }


def test_legacy_flat_state_adopted_into_first_workspace(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "renames.json").write_text(_json.dumps({"111": "My Custom Name"}), encoding="utf-8")

    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})

    moved = ws / "state" / "export" / "renames.json"
    assert moved.exists()
    assert _json.loads(moved.read_text()) == {"111": "My Custom Name"}
    assert not (ws / "renames.json").exists()        # moved, not copied
    assert (ws / ".migrated").exists()
