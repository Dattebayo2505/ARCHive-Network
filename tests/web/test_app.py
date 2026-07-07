from fastapi.testclient import TestClient

from archivenetwork.app import create_app


def test_health():
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"name": "archivenetwork", "status": "ok"}


def test_cors_allows_ui_origin():
    client = TestClient(create_app())
    resp = client.get("/", headers={"Origin": "http://localhost:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_allows_any_localhost_port():
    """Vite falls back to :5174/:5175/… when :5173 is taken — any localhost port
    (and 127.0.0.1) must be allowed so the UI keeps working."""
    client = TestClient(create_app())
    for origin in ("http://localhost:5174", "http://127.0.0.1:4173", "http://localhost:61234"):
        # Simple GET carries the Origin back.
        resp = client.get("/", headers={"Origin": origin})
        assert resp.headers.get("access-control-allow-origin") == origin, origin
        # Preflight (the OPTIONS the browser sends before a JSON POST) must pass.
        pre = client.options(
            "/api/ingest/folder",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert pre.status_code == 200, origin


def test_cors_blocks_foreign_origin():
    """A non-local origin must NOT get CORS access (don't open to the world)."""
    client = TestClient(create_app())
    resp = client.get("/", headers={"Origin": "http://evil.example"})
    assert resp.headers.get("access-control-allow-origin") is None
