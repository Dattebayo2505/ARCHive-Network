import socket
import time

from archivenetwork.loader.storage import EndpointProbe, probe_endpoint


def _closed_port() -> int:
    """A port that was bound and then released — nothing is listening on it now."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_probe_reports_reachable_when_something_is_listening():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        probe = probe_endpoint(f"http://127.0.0.1:{port}")
    finally:
        server.close()
    assert probe == EndpointProbe(reachable=True, reason=None)


def test_probe_reports_unreachable_with_a_reason_on_a_closed_port():
    probe = probe_endpoint(f"http://127.0.0.1:{_closed_port()}")
    assert probe.reachable is False
    assert probe.reason  # a non-empty explanation, whatever the OS worded it as


def test_probe_is_bounded_and_never_hangs():
    # 10.255.255.1 is non-routable: without a timeout this blocks for the OS default,
    # which is ~21s per address on Windows. db.py learned this the hard way — a test
    # file went from 6s to 135s before CONNECT_TIMEOUT existed.
    started = time.monotonic()
    probe = probe_endpoint("http://10.255.255.1:4566", timeout=0.25)
    elapsed = time.monotonic() - started
    assert probe.reachable is False
    assert elapsed < 5


def test_probe_returns_a_result_for_a_malformed_url_instead_of_raising():
    probe = probe_endpoint("not-a-url")
    assert probe.reachable is False
    assert probe.reason
