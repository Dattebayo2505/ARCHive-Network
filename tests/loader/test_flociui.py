"""Warming the Floci UI, and choosing between the deep link and the poller.

The behaviour under test is the one that was *measured* against a real floci, not assumed:
only the poller page creates the sibling container, so a bare deep link is dead on a cold
machine. Everything here stubs the two HTTP calls; no container is involved.
"""

from __future__ import annotations

import urllib.error

import pytest

from archivenetwork.loader import flociui

ENDPOINT = "http://127.0.0.1:4566"
EXPLORER = "http://127.0.0.1:4500/cloud-explorer/aws/storage"
POLLER = "http://127.0.0.1:4566/_floci/ui"


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch):
    monkeypatch.setattr(flociui.time, "sleep", lambda _s: None)


@pytest.fixture
def http(monkeypatch):
    """Record every URL fetched and reply from a scripted sequence of status bodies."""
    fetched: list[str] = []

    def install(statuses):
        queue = list(statuses)

        def _get(url, timeout=flociui._REQUEST_TIMEOUT):
            fetched.append(url)
            if url.endswith(flociui.STATUS_PATH):
                body = queue.pop(0) if len(queue) > 1 else queue[0]
                return None if body is None else __import__("json").dumps(body)
            return "<html>the poller page</html>"

        monkeypatch.setattr(flociui, "_get", _get)

    return fetched, install


# --- URL shapes --------------------------------------------------------------------------


def test_the_explorer_lives_on_the_ui_containers_own_port():
    """4500, not the S3 endpoint's 4566 — it is a separate container; only the host is shared."""
    assert flociui.explorer_url(ENDPOINT) == EXPLORER
    assert flociui.poller_url(ENDPOINT) == POLLER


def test_a_relocated_endpoint_keeps_its_host_but_not_its_port():
    assert flociui.explorer_url("http://floci.local:9999") == (
        "http://floci.local:4500/cloud-explorer/aws/storage"
    )
    assert flociui.poller_url("http://floci.local:9999") == "http://floci.local:9999/_floci/ui"


def test_a_malformed_endpoint_falls_back_to_the_documented_default():
    assert flociui.explorer_url("") == EXPLORER
    assert flociui.poller_url("") == POLLER


# --- ensure ------------------------------------------------------------------------------


def test_an_already_running_ui_short_circuits_to_the_deep_link(http):
    fetched, install = http
    install([{"ready": True, "url": "http://127.0.0.1:4500/"}])
    state = flociui.ensure(ENDPOINT)
    assert state.ready is True
    assert state.url == EXPLORER
    assert fetched == [ENDPOINT + flociui.STATUS_PATH], "must not start anything when it is up"


def test_a_cold_ui_is_warmed_through_the_poller_then_deep_linked(http):
    fetched, install = http
    install([{"ready": False, "url": None}, {"ready": True, "url": "http://127.0.0.1:4500/"}])
    state = flociui.ensure(ENDPOINT)
    assert state.ready is True
    assert state.url == EXPLORER
    # Measured against a real floci: the STATUS endpoint reports but never creates the
    # container — only fetching the poller page does. Dropping this line makes the deep link
    # dead on a cold machine.
    assert POLLER in fetched


def test_a_ui_that_never_comes_up_falls_back_to_the_poller_not_a_dead_link(http):
    _, install = http
    install([{"ready": False, "url": None}])
    state = flociui.ensure(ENDPOINT, wait=1.0)
    assert state.ready is False
    assert state.url == POLLER, "the poller always renders; :4500 would refuse the connection"
    assert state.explorer == EXPLORER, "the deep link is still reported, just not chosen"
    assert state.reason


def test_floci_being_down_does_not_burn_the_wait_budget(http):
    fetched, install = http
    install([None])
    state = flociui.ensure(ENDPOINT, wait=30.0)
    assert state.ready is False
    assert state.url == POLLER
    assert "down" in state.reason
    assert fetched == [ENDPOINT + flociui.STATUS_PATH], "no warm attempt against a dead floci"


def test_flocis_own_error_is_surfaced_rather_than_replaced(http):
    _, install = http
    install([{"ready": False, "url": None, "error": "java.net.SocketException"}])
    state = flociui.ensure(ENDPOINT, wait=1.0)
    assert state.reason == "java.net.SocketException"


def test_a_non_json_status_body_is_not_a_crash(monkeypatch):
    monkeypatch.setattr(flociui, "_get", lambda url, timeout=5.0: "<html>nope</html>")
    state = flociui.ensure(ENDPOINT, wait=0)
    assert state.ready is False
    assert state.url == POLLER


@pytest.mark.parametrize(
    "exc",
    [
        urllib.error.URLError("refused"),
        OSError("connection reset"),
        ValueError("unknown url type"),
    ],
)
def test_get_swallows_the_failures_a_dead_endpoint_actually_raises(monkeypatch, exc):
    """`_get` is the only place these can surface, so `ensure` above never needs a try."""

    def boom(url, timeout=None):
        raise exc

    monkeypatch.setattr(flociui.urllib.request, "urlopen", boom)
    assert flociui._get("http://127.0.0.1:1/nope") is None


def test_get_really_returns_none_against_a_closed_port():
    """No stubbing at all — port 1 is not listening, and this must be an answer, not a raise."""
    assert flociui._get("http://127.0.0.1:1/nope", timeout=1.0) is None
