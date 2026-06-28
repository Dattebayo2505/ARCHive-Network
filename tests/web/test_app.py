from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_index_renders():
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Streamlinify" in resp.text
