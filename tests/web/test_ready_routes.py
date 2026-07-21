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
