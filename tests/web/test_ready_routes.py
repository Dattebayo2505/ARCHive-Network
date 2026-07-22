from pathlib import Path

from fastapi.testclient import TestClient

import archivenetwork.web.routes_ready as ready_mod
from archivenetwork.app import create_app
from archivenetwork.inventory.parser import build_inventory
from archivenetwork.transform.builder import build_ready_folder


def _build_into_ready(export_root: Path, tmp_path: Path, name: str = "mybuild") -> None:
    inv = build_inventory(export_root)
    keep = {p.fbid for p in inv.all_photos() if not p.is_video}
    build_ready_folder(export_root, tmp_path / "workspace" / "ready" / name, keep)


def test_list_ready_returns_built_folder(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _build_into_ready(export_root, tmp_path)
    client = TestClient(create_app())
    resp = client.get("/api/ready")
    assert resp.status_code == 200
    builds = resp.json()["builds"]
    assert len(builds) == 1
    assert builds[0]["id"] == "mybuild"
    assert builds[0]["size_bytes"] > 0
    assert builds[0]["photos"] >= 1
    assert builds[0]["albums"] >= 1


def test_list_ready_empty_when_no_ready_dir(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    assert client.get("/api/ready").json() == {"builds": []}


def test_current_ready_404s_without_a_session(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    assert client.get("/api/ready/current").status_code == 404


def test_current_ready_is_null_before_a_build(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    assert client.get("/api/ready/current").json() == {"build": None}


def test_current_ready_reports_the_build_after_building(
    export_root: Path, tmp_path: Path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("archivenetwork.web.routes_build.reveal_path", lambda p: None)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})
    client.post("/api/build")

    build = client.get("/api/ready/current").json()["build"]
    # Named from the workspace id, not the generic extracted-root name.
    assert build["id"] == "export"
    assert build["size_bytes"] > 0
    assert build["photos"] >= 1


def test_current_ready_ignores_other_workspaces_builds(
    export_root: Path, tmp_path: Path, monkeypatch
):
    """A build belonging to a *different* workspace must not read as "already built"
    for the loaded one — the overwrite warning would be a lie."""
    monkeypatch.chdir(tmp_path)
    _build_into_ready(export_root, tmp_path, name="someone-elses-build")
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    assert client.get("/api/ready/current").json() == {"build": None}


def test_reveal_build_ok(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _build_into_ready(export_root, tmp_path)
    seen = {}
    monkeypatch.setattr(ready_mod, "reveal_path", lambda p: seen.setdefault("path", p))
    client = TestClient(create_app())
    resp = client.post("/api/ready/reveal", json={"id": "mybuild"})
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert seen["path"].name == "mybuild"


def test_reveal_unknown_build_404(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "workspace" / "ready").mkdir(parents=True)
    client = TestClient(create_app())
    assert client.post("/api/ready/reveal", json={"id": "ghost"}).status_code == 404


def test_reveal_rejects_traversal(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "workspace" / "ready").mkdir(parents=True)
    client = TestClient(create_app())
    assert client.post("/api/ready/reveal", json={"id": ".."}).status_code == 404


def test_delete_build_removes_the_folder(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _build_into_ready(export_root, tmp_path)
    ready = tmp_path / "workspace" / "ready" / "mybuild"
    assert ready.is_dir()
    client = TestClient(create_app())
    resp = client.post("/api/ready/delete", json={"id": "mybuild"})
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert not ready.exists()
    assert client.get("/api/ready").json() == {"builds": []}


def test_delete_build_keeps_the_export_and_the_selection(
    export_root: Path, tmp_path: Path, monkeypatch
):
    """Deleting the output must cost nothing but the copy on disk — the same picks
    have to rebuild the identical folder."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("archivenetwork.web.routes_build.reveal_path", lambda p: None)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})
    client.post("/api/build")

    build_id = client.get("/api/ready/current").json()["build"]["id"]
    assert client.post("/api/ready/delete", json={"id": build_id}).status_code == 200

    assert export_root.is_dir()
    assert client.get("/api/ready/current").json() == {"build": None}
    # The pick survived, so a second build reproduces the folder.
    client.post("/api/build")
    assert client.get("/api/ready/current").json()["build"]["id"] == build_id


def test_delete_unknown_build_404(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "workspace" / "ready").mkdir(parents=True)
    client = TestClient(create_app())
    assert client.post("/api/ready/delete", json={"id": "ghost"}).status_code == 404


def test_delete_rejects_traversal(export_root: Path, tmp_path: Path, monkeypatch):
    """".." resolves to workspace/, a real directory — the guard must reject it on
    "not a direct child", not on "does not exist", or delete could walk out of ready/."""
    monkeypatch.chdir(tmp_path)
    _build_into_ready(export_root, tmp_path)
    client = TestClient(create_app())
    assert client.post("/api/ready/delete", json={"id": ".."}).status_code == 404
    assert (tmp_path / "workspace" / "ready").is_dir()
