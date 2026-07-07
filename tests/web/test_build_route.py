from pathlib import Path

from fastapi.testclient import TestClient

from archivenetwork.app import create_app
from archivenetwork.reveal import RevealError


def test_build_produces_ready_folder(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    revealed: list[Path] = []
    monkeypatch.setattr(
        "archivenetwork.web.routes_build.reveal_path", lambda p: revealed.append(p)
    )
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})
    client.post("/api/toggle", json={"album_fbid": "__non_album__", "photo_fbid": "m01"})

    resp = client.post("/api/build")
    assert resp.status_code == 200
    body = resp.json()
    assert "copied" in body
    assert body["albums_written"] >= 1

    ready = tmp_path / "workspace" / "ready" / "export"
    assert (ready / "posts" / "album" / "0.json").exists()
    # m01 was toggled so it should exist
    assert (ready / "posts" / "media" / "Mobileuploads_999" / "m01.jpg").exists()
    # The build pops the file manager open on the workspace/ready/ parent.
    assert [p.resolve() for p in revealed] == [ready.parent.resolve()]


def test_build_survives_reveal_failure(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def _boom(_path: Path) -> None:
        raise RevealError("no file manager here")

    monkeypatch.setattr("archivenetwork.web.routes_build.reveal_path", _boom)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})

    resp = client.post("/api/build")
    assert resp.status_code == 200
    # The build still completed despite reveal failing.
    ready = tmp_path / "workspace" / "ready" / "export"
    assert (ready / "posts" / "album" / "0.json").exists()
