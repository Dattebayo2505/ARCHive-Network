"""The Docker routes never shell out under test — `dockerctl` is stubbed wholesale.

What matters at this layer is the *contract*: status always answers, an unusable Docker is a
409 rather than a 500, an unknown verb is a 422, and every action reply carries a fresh
reading so the panel re-renders from docker's view instead of from its own optimism.
"""

from __future__ import annotations

import pytest

from archivenetwork.app import create_app
from archivenetwork.loader.dockerctl import CommandOutcome, DockerState
from archivenetwork.loader.flociui import UiState
from archivenetwork.web import routes_docker
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    return TestClient(create_app())


def _state(**over) -> DockerState:
    base = dict(
        installed=True,
        engine_up=True,
        compose_available=True,
        compose_file=True,
        container="running",
        reason=None,
    )
    return DockerState(**{**base, **over})


def _stub(monkeypatch, state: DockerState, outcome: CommandOutcome | None = None):
    monkeypatch.setattr(routes_docker.dockerctl, "probe", lambda: state)
    if outcome is not None:
        monkeypatch.setattr(routes_docker.dockerctl, "run_action", lambda action: outcome)


def test_status_answers_even_when_docker_is_missing(client, monkeypatch):
    _stub(
        monkeypatch,
        _state(installed=False, engine_up=False, compose_available=False, container=None,
               reason="Docker isn't installed"),
    )
    res = client.get("/api/docker/status")
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is False
    assert body["installed"] is False
    assert body["reason"] == "Docker isn't installed"


def test_status_separates_installed_engine_and_container(client, monkeypatch):
    _stub(monkeypatch, _state(container="exited"))
    body = client.get("/api/docker/status").json()
    assert body["available"] is True
    assert body["running"] is False
    assert body["exists"] is True
    assert body["container"] == "exited"
    assert body["container_name"] == "archivenetwork-floci"


@pytest.mark.parametrize("action", ["start", "restart", "stop", "rebuild"])
def test_every_action_runs_and_returns_a_fresh_reading(client, monkeypatch, action):
    _stub(monkeypatch, _state(), CommandOutcome(ok=True, code=0, output="Container Started"))
    body = client.post(f"/api/docker/floci?action={action}").json()
    assert body["action"] == action
    assert body["ok"] is True
    assert body["docker"]["running"] is True


def test_an_unknown_action_is_a_422_not_a_default(client, monkeypatch):
    _stub(monkeypatch, _state(), CommandOutcome(ok=True, code=0, output=""))
    assert client.post("/api/docker/floci?action=obliterate").status_code == 422
    assert client.post("/api/docker/floci").status_code == 422


def test_actions_are_refused_when_docker_is_unusable(client, monkeypatch):
    _stub(
        monkeypatch,
        _state(engine_up=False, compose_available=False, container=None,
               reason="Docker Desktop isn't running."),
    )
    called = []
    monkeypatch.setattr(
        routes_docker.dockerctl, "run_action", lambda a: called.append(a) or CommandOutcome(True, 0, "")
    )
    res = client.post("/api/docker/floci?action=start")
    assert res.status_code == 409
    assert res.json()["detail"] == "Docker Desktop isn't running."
    assert called == [], "a stale frontend must not be able to shell out anyway"


def test_a_missing_compose_file_names_itself(client, monkeypatch):
    _stub(monkeypatch, _state(compose_file=False, reason=None))
    res = client.post("/api/docker/floci?action=start")
    assert res.status_code == 409
    assert "docker-compose.yml" in res.json()["detail"]


def test_a_failed_command_is_a_200_carrying_the_failure(client, monkeypatch):
    """The command ran; it just didn't work. That is a result to render, not an HTTP error —
    the same reasoning that keeps an upload's `orphans` out of the status code."""
    _stub(
        monkeypatch,
        _state(container="exited"),
        CommandOutcome(ok=False, code=1, output="Error: port 4566 is already allocated"),
    )
    res = client.post("/api/docker/floci?action=start")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "already allocated" in body["output"]
    assert body["docker"]["running"] is False


def test_the_docker_routes_need_no_session(client, monkeypatch):
    """No export loaded, no database — the container is a machine-level thing."""
    _stub(monkeypatch, _state(), CommandOutcome(ok=True, code=0, output=""))
    assert client.get("/api/docker/status").status_code == 200
    assert client.post("/api/docker/floci?action=restart").status_code == 200


# --- /api/docker/floci-ui ----------------------------------------------------------------


def _ui(**over):
    base = dict(
        ready=True,
        url="http://127.0.0.1:4500/cloud-explorer/aws/storage",
        explorer="http://127.0.0.1:4500/cloud-explorer/aws/storage",
        poller="http://127.0.0.1:4566/_floci/ui",
        reason=None,
    )
    return UiState(**{**base, **over})


def test_the_ui_route_returns_the_storage_explorer_when_it_is_up(client, monkeypatch):
    monkeypatch.setattr(routes_docker.flociui, "ensure", lambda endpoint: _ui())
    body = client.get("/api/docker/floci-ui").json()
    assert body["ready"] is True
    assert body["url"].endswith("/cloud-explorer/aws/storage")
    assert ":4500" in body["url"], "the UI is a sibling container on its own port"


def test_the_ui_route_hands_back_the_poller_rather_than_a_dead_deep_link(client, monkeypatch):
    """:4500 refuses the connection until the sibling container exists; the poller is what
    creates it, and it always renders something."""
    monkeypatch.setattr(
        routes_docker.flociui,
        "ensure",
        lambda endpoint: _ui(ready=False, url="http://127.0.0.1:4566/_floci/ui",
                             reason="not started"),
    )
    body = client.get("/api/docker/floci-ui").json()
    assert body["ready"] is False
    assert body["url"].endswith("/_floci/ui")
    assert body["explorer"].endswith("/cloud-explorer/aws/storage"), "still reported, just not chosen"


def test_the_ui_route_uses_the_configured_endpoint_and_owns_its_wait(client, monkeypatch):
    """The wait budget belongs to `flociui.DEFAULT_WAIT`, not to the caller: a query-string
    sleep on a server route is a lever no client ever pulls."""
    seen = {}

    def ensure(endpoint):
        seen.update(endpoint=endpoint)
        return _ui()

    monkeypatch.setattr(routes_docker.flociui, "ensure", ensure)
    monkeypatch.setattr(routes_docker.settings, "floci_endpoint_url", "http://floci.local:9999")
    client.get("/api/docker/floci-ui?wait=2")
    assert seen == {"endpoint": "http://floci.local:9999"}


def test_the_ui_route_needs_no_docker_probe(client, monkeypatch):
    """It asks floci, not the daemon — so it must not 409 the way the action route does."""
    monkeypatch.setattr(routes_docker.dockerctl, "probe", lambda: _state(engine_up=False))
    monkeypatch.setattr(routes_docker.flociui, "ensure", lambda endpoint: _ui())
    assert client.get("/api/docker/floci-ui").status_code == 200
