from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_health():
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"name": "streamlinify", "status": "ok"}


def test_cors_allows_ui_origin():
    client = TestClient(create_app())
    resp = client.get("/", headers={"Origin": "http://localhost:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
