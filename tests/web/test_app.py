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


def test_cors_allows_every_method_the_api_actually_serves():
    """The preflight allow-list must be derived from the routes, not guessed.

    `allow_methods` used to be a hardcoded ["GET", "POST", "OPTIONS"], so `DELETE
    /api/dev/database` — the API's only DELETE — failed its preflight with
    `400 Disallowed CORS method` and the Dev panel's "Drop database" button did nothing.
    The backend route was fine; the browser never got to call it.

    Asserting against the live route table (rather than hardcoding DELETE) means the next
    PUT/PATCH route added anywhere is covered the moment it exists.
    """
    app = create_app()
    client = TestClient(app)
    # Read the methods off the OpenAPI schema, not `app.routes`: since FastAPI 0.138 an
    # included router is wrapped in a private `_IncludedRouter` that exposes neither `.methods`
    # nor `.routes`, so walking the route table silently sees only the four built-in docs
    # endpoints — a false pass. The schema is public API and lists every path it serves.
    served = {
        m.upper()
        for methods in app.openapi()["paths"].values()
        for m in methods
        if m.upper() not in ("HEAD", "OPTIONS")
    }
    assert "DELETE" in served, "guard: the route this regression is about must still exist"

    for method in sorted(served):
        pre = client.options(
            "/api/dev/database",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": method,
            },
        )
        assert pre.status_code == 200, f"{method} preflight: {pre.status_code} {pre.text}"


def test_cors_blocks_foreign_origin():
    """A non-local origin must NOT get CORS access (don't open to the world)."""
    client = TestClient(create_app())
    resp = client.get("/", headers={"Origin": "http://evil.example"})
    assert resp.headers.get("access-control-allow-origin") is None
