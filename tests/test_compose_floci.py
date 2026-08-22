"""The compose file is a load-bearing artifact, not documentation.

`docker-compose.yml` is checked in on purpose (the Dev panel's Docker-down message points
users at `docker compose up -d`), so the things the emulator needs to actually work belong
under test the same way the code is.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = REPO_ROOT / "docker-compose.yml"

DOCKER_SOCK = "/var/run/docker.sock"


def _floci_service() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["floci"]


def test_compose_file_is_checked_in():
    assert COMPOSE.is_file(), "the Docker-down message tells users to run `docker compose up -d`"


def test_floci_publishes_the_configured_port():
    assert "4566:4566" in _floci_service()["ports"]


def test_floci_mounts_the_container_runtime_socket():
    """Without this the S3 API works but `/_floci/ui` dies with a SocketException.

    floci starts its UI as a *sibling* container (`floci/floci-ui`, port 4500) rather than
    serving it in-process, so it needs to reach the host container runtime. Dropping this
    mount does not break a single upload — which is exactly why it went unnoticed.
    """
    volumes = _floci_service()["volumes"]
    targets = {v.split(":")[1] for v in volumes}
    assert DOCKER_SOCK in targets, f"expected a {DOCKER_SOCK} bind-mount, got {volumes}"
    assert "/app/data" in targets


def test_floci_persists_its_objects_to_the_mounted_path():
    """Without this the bind-mount below it is decorative and every restart empties the bucket.

    The image already sets FLOCI_STORAGE_PERSISTENT_PATH=/app/data, so the volume looks
    sufficient — but floci defaults to `Storage: memory` and writes nothing there. Measured:
    158 uploaded objects, `docker compose restart floci`, NoSuchBucket. The Dev panel's
    Restart and Rebuild buttons make that a one-click loss, which is why this is pinned.
    """
    service = _floci_service()
    assert service.get("environment", {}).get("FLOCI_STORAGE_MODE") == "persistent"
    targets = {v.split(":")[1] for v in service["volumes"]}
    assert "/app/data" in targets, "persistence needs somewhere on the host to persist to"
