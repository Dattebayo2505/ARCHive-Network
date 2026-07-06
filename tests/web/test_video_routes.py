from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def _loaded_client(export_root: Path, tmp_path, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    return client


def test_video_stream_served(video_export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(video_export_root, tmp_path, monkeypatch)
    resp = client.get("/api/video/v01")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("video/")
    assert resp.content.startswith(b"\x00\x00\x00\x18ftyp")


def test_video_stream_supports_range(video_export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(video_export_root, tmp_path, monkeypatch)
    resp = client.get("/api/video/v01", headers={"Range": "bytes=0-3"})
    assert resp.status_code == 206
    assert len(resp.content) == 4


def test_video_stream_unknown_404(video_export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(video_export_root, tmp_path, monkeypatch)
    assert client.get("/api/video/nope").status_code == 404


def test_thumbnail_missing_then_saved(video_export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(video_export_root, tmp_path, monkeypatch)
    assert client.get("/api/video/v01/thumbnail").status_code == 404
    save = client.post("/api/video/v01/thumbnail", content=b"JPEGBYTES",
                       headers={"content-type": "image/jpeg"})
    assert save.status_code == 200 and save.json() == {"ok": True}
    got = client.get("/api/video/v01/thumbnail")
    assert got.status_code == 200 and got.content == b"JPEGBYTES"


def test_save_thumbnail_unknown_video_404(video_export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(video_export_root, tmp_path, monkeypatch)
    assert client.post("/api/video/nope/thumbnail", content=b"X").status_code == 404


def test_video_route_cors_header(video_export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(video_export_root, tmp_path, monkeypatch)
    resp = client.get("/api/video/v01", headers={"Origin": "http://localhost:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
