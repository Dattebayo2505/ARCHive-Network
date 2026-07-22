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
    # Non-album photos are disregarded: the toggle is refused, not merely uncounted.
    refused = client.post("/api/toggle", json={"album_fbid": "__non_album__", "photo_fbid": "m01"})
    assert refused.status_code == 409
    assert refused.json()["error"] == "disregarded"

    resp = client.post("/api/build")
    assert resp.status_code == 200
    body = resp.json()
    assert "copied" in body
    assert body["albums_written"] >= 1
    assert body["non_album_skipped"] == 2

    ready = tmp_path / "workspace" / "ready" / "export"
    assert (ready / "posts" / "album" / "0.json").exists()
    # m01 could not be picked, so it is not in the build.
    assert not (ready / "posts" / "media" / "Mobileuploads_999" / "m01.jpg").exists()
    # The build pops the file manager open on the workspace/ready/ parent.
    assert [p.resolve() for p in revealed] == [ready.parent.resolve()]


def test_build_with_no_selection_keeps_nothing(export_root: Path, tmp_path: Path, monkeypatch):
    """The route must not auto-keep non-album photos (or anything else). Ingest, toggle
    nothing, build — and get an empty result."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("archivenetwork.web.routes_build.reveal_path", lambda p: None)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})

    body = client.post("/api/build").json()
    assert body["copied"] == 0
    assert body["albums_written"] == 0
    assert body["videos_built"] == 0

    ready = tmp_path / "workspace" / "ready" / "export"
    assert not any((ready / "posts" / "media").rglob("*.jpg"))


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
