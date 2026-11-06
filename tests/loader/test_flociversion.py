"""Is the local floci the latest release? Three readings, compared without ever raising.

The running version comes from floci's own `/_floci/health`, the pinned one from the
checked-in `docker-compose.yml`, and the latest from GitHub's newest non-prerelease. Every
network read is stubbed here: a test must never depend on GitHub being reachable.
"""

from __future__ import annotations

import json

import pytest

from archivenetwork.loader import flociversion
from archivenetwork.loader.dockerctl import COMPOSE_FILE


@pytest.fixture
def http(monkeypatch):
    """Route `_get` to canned bodies by URL suffix; anything unlisted is unreachable (None)."""
    bodies: dict[str, str] = {}
    monkeypatch.setattr(flociversion, "_get", lambda url, timeout=0: next(
        (b for suffix, b in bodies.items() if url.endswith(suffix)), None))
    flociversion._latest_cache.clear()
    return bodies


@pytest.mark.parametrize("raw, parsed", [
    ("2.4.0", (2, 4, 0)), ("v2.10.1", (2, 10, 1)), ("2.4.0-compat", (2, 4, 0)),
    ("latest", None), ("nightly", None), (None, None), ("", None),
])
def test_versions_parse_to_comparable_tuples(raw, parsed):
    assert flociversion.parse(raw) == parsed


def test_the_checked_in_compose_file_pins_a_floci_version_with_dynamodb_persistence():
    # A floating `latest` is never re-pulled by compose, which is how this machine sat on
    # 1.7.0, a release that drops DynamoDB tables on restart, for two months.
    pinned = flociversion.parse(flociversion.pinned_version(COMPOSE_FILE))
    assert pinned is not None and pinned >= (2, 0, 0)


def test_the_pin_is_read_from_the_image_line(tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  floci:\n    # note\n    image: floci/floci:2.3.0 # c\n")
    assert flociversion.pinned_version(compose) == "2.3.0"
    assert flociversion.pinned_version(tmp_path / "missing.yml") is None


def test_running_version_comes_from_flocis_health_endpoint(http):
    http["/_floci/health"] = json.dumps({"version": "2.4.0", "services": {}})
    assert flociversion.running_version("http://127.0.0.1:4566") == "2.4.0"


def test_a_down_floci_has_no_running_version(http):
    assert flociversion.running_version("http://127.0.0.1:4566") is None


def test_latest_version_is_githubs_newest_release_and_is_cached(http):
    http["/releases/latest"] = json.dumps({"tag_name": "v2.5.0"})
    assert flociversion.latest_version() == "2.5.0"
    http.clear()  # a second call inside the TTL must not go back to the network
    assert flociversion.latest_version() == "2.5.0"


def test_an_unreachable_github_is_an_unknown_latest_not_an_error(http):
    http["/releases/latest"] = "not json"
    assert flociversion.latest_version() is None


@pytest.mark.parametrize("running, pinned, latest, status", [
    ("2.4.0", "2.4.0", "2.4.0", "up_to_date"),
    (None, "2.4.0", "2.4.0", "up_to_date"),
    ("2.4.0", "2.4.0", "2.5.0", "update_available"),
    ("1.7.0", "2.4.0", "2.4.0", "mismatch"),
    ("2.4.0", "latest", "2.4.0", "not_pinned"),
    ("2.4.0", "2.4.0", None, "unknown"),
])
def test_assess(running, pinned, latest, status):
    report = flociversion.assess(running, pinned, latest)
    assert report.status == status
    assert report.message  # every status explains itself in one line


def test_an_available_update_names_the_command_to_run():
    message = flociversion.assess("2.4.0", "2.4.0", "2.5.0").message
    assert "2.5.0" in message and "docker compose pull" in message


def test_a_stale_container_is_reported_even_when_the_pin_is_current():
    # The pin says 2.4.0 but the container predates the pin: `up -d` was never re-run.
    message = flociversion.assess("1.7.0", "2.4.0", "2.4.0").message
    assert "1.7.0" in message and "docker compose up -d" in message
