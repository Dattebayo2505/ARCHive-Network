"""Lifecycle control for the local floci container, driven through the `docker` CLI.

The floci upload target is inert while its container is down, and until now the only way out
was a message telling a volunteer to open a terminal and type `docker compose up -d`. That is
the one instruction in this tool that assumes the reader is a developer. This module removes
the assumption: it probes for Docker and runs `docker compose` against the repo's checked-in
`docker-compose.yml` on the panel's behalf.

It shells out to the **CLI** rather than talking to the daemon socket directly, on purpose:
the host endpoint is a named pipe on Windows and a unix socket everywhere else, and the CLI
already abstracts that difference away (the same reason `docker-compose.yml` can name the
literal `/var/run/docker.sock` on every platform).

Every command is bounded by a timeout and never raises out of `_run` — a dead daemon, a
missing binary and a hung pull all have to arrive at the panel as an *answer*, not a 500.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Literal

from ..config import PROJECT_ROOT

# The service and container names are the compose file's, not ours to invent: `docker inspect`
# is keyed on the fixed `container_name:`, which is what makes state readable without parsing
# `compose ps` JSON. `tests/test_compose_floci.py` pins both.
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
SERVICE = "floci"
CONTAINER_NAME = "archivenetwork-floci"

Action = Literal["start", "restart", "stop", "rebuild"]

# `docker info` round-trips to the daemon and is the slow one; a first `up` may pull ~500 MB
# and `rebuild` always re-pulls, so its ceiling is minutes, not seconds.
PROBE_TIMEOUT = 20.0
_TIMEOUTS: dict[str, float] = {
    "start": 240.0,
    "restart": 120.0,
    "stop": 120.0,
    "rebuild": 900.0,
}

# `stop`, not `down`: `down` removes the container, so the next Start pays full creation cost
# and the panel loses the "exited" state that tells it Restart is even meaningful. Data lives
# in a bind mount either way, so neither is destructive.
_ARGV: dict[str, list[str]] = {
    "start": ["compose", "-f", "{compose}", "up", "-d", SERVICE],
    "restart": ["compose", "-f", "{compose}", "restart", SERVICE],
    "stop": ["compose", "-f", "{compose}", "stop", SERVICE],
    # --pull always is the whole point of Rebuild: `up -d` alone reuses the cached image, so
    # without it the button would be an expensive no-op.
    "rebuild": [
        "compose",
        "-f",
        "{compose}",
        "up",
        "-d",
        "--pull",
        "always",
        "--force-recreate",
        SERVICE,
    ],
}


@dataclass(frozen=True)
class CommandOutcome:
    ok: bool
    code: int
    output: str


@dataclass(frozen=True)
class DockerState:
    """What the panel is allowed to offer, and what the container is doing right now.

    The four booleans are separate questions on purpose, exactly as `server_up` and
    `database_exists` are in `loader/db.py`: "Docker is not installed", "Docker Desktop is
    not running" and "the container has never been created" need three different sentences
    on screen, and one merged flag could only produce one.
    """

    installed: bool
    engine_up: bool
    compose_available: bool
    compose_file: bool
    container: str | None  # docker's own State.Status ('running' | 'exited' | ...) or None
    reason: str | None = None

    @property
    def available(self) -> bool:
        """Whether the controls may be offered at all."""
        return self.installed and self.engine_up and self.compose_available and self.compose_file

    @property
    def running(self) -> bool:
        return self.container == "running"

    @property
    def exists(self) -> bool:
        return self.container is not None

    def as_dict(self) -> dict:
        return {
            "installed": self.installed,
            "engine_up": self.engine_up,
            "compose_available": self.compose_available,
            "compose_file": self.compose_file,
            "available": self.available,
            "container": self.container,
            "running": self.running,
            "exists": self.exists,
            "service": SERVICE,
            "container_name": CONTAINER_NAME,
            "reason": self.reason,
        }


def _tail(output: str, lines: int = 12) -> str:
    """The last few lines of a command's output — enough to diagnose, short enough to show."""
    kept = [line for line in output.strip().splitlines() if line.strip()]
    return "\n".join(kept[-lines:])


def _run(argv: list[str], timeout: float) -> CommandOutcome:
    """Run `argv`, never raise. A missing binary and a hung daemon are both *answers* here."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, no user-supplied strings
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return CommandOutcome(ok=False, code=127, output="The `docker` command isn't on PATH.")
    except subprocess.TimeoutExpired:
        label = " ".join(argv[1:3])
        return CommandOutcome(
            ok=False,
            code=124,
            output=f"`docker {label}` didn't finish within {int(timeout)}s.",
        )
    except OSError as exc:  # pragma: no cover - platform-specific spawn failures
        return CommandOutcome(ok=False, code=1, output=str(exc))
    return CommandOutcome(
        ok=proc.returncode == 0,
        code=proc.returncode,
        # compose writes its progress to stderr even on success, so both streams matter.
        output=f"{proc.stdout}{proc.stderr}",
    )


def docker_exe() -> str | None:
    return shutil.which("docker")


def probe() -> DockerState:
    """Answer all four questions in one pass. Never raises."""
    exe = docker_exe()
    if exe is None:
        return DockerState(
            installed=False,
            engine_up=False,
            compose_available=False,
            compose_file=COMPOSE_FILE.is_file(),
            container=None,
            reason="Docker isn't installed, or `docker` isn't on this machine's PATH.",
        )

    info = _run([exe, "info", "--format", "{{.ServerVersion}}"], PROBE_TIMEOUT)
    if not info.ok:
        return DockerState(
            installed=True,
            engine_up=False,
            compose_available=False,
            compose_file=COMPOSE_FILE.is_file(),
            container=None,
            reason=_tail(info.output, 4) or "The Docker engine isn't responding.",
        )

    compose_available = _run([exe, "compose", "version"], PROBE_TIMEOUT).ok
    status = _run([exe, "inspect", "-f", "{{.State.Status}}", CONTAINER_NAME], PROBE_TIMEOUT)
    return DockerState(
        installed=True,
        engine_up=True,
        compose_available=compose_available,
        compose_file=COMPOSE_FILE.is_file(),
        # A non-zero exit here means "no such container" — absent, not broken.
        container=(status.output.strip() or None) if status.ok else None,
        reason=(
            None
            if compose_available
            else "Docker is running, but the `docker compose` plugin isn't installed."
        ),
    )


def run_action(action: Action) -> CommandOutcome:
    """Run one compose lifecycle command. Assumes `probe().available`; the route enforces it."""
    exe = docker_exe()
    if exe is None:
        return CommandOutcome(ok=False, code=127, output="The `docker` command isn't on PATH.")
    argv = [exe, *(part.format(compose=COMPOSE_FILE) for part in _ARGV[action])]
    outcome = _run(argv, _TIMEOUTS[action])
    return CommandOutcome(ok=outcome.ok, code=outcome.code, output=_tail(outcome.output))
