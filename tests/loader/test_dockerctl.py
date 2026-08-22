"""`dockerctl` is a shell-out, so what is worth testing is the *argv it builds* and the
*answers it gives when the shell-out fails* — not Docker itself.

Every test stubs `_run`, so the suite never needs a Docker daemon and never mutates the
developer's containers. The one exception is `_run`'s own error handling, which is exercised
against a binary that genuinely does not exist.
"""

from __future__ import annotations

import subprocess

import pytest

from archivenetwork.loader import dockerctl
from archivenetwork.loader.dockerctl import CommandOutcome


@pytest.fixture
def fake_docker(monkeypatch):
    """Pretend `docker` is on PATH and record every argv `dockerctl` builds."""
    monkeypatch.setattr(dockerctl, "docker_exe", lambda: "/usr/bin/docker")
    calls: list[list[str]] = []

    def install(responder):
        def _run(argv, timeout):
            calls.append(argv)
            return responder(argv)

        monkeypatch.setattr(dockerctl, "_run", _run)

    return calls, install


def _ok(output=""):
    return CommandOutcome(ok=True, code=0, output=output)


def _fail(output="boom", code=1):
    return CommandOutcome(ok=False, code=code, output=output)


# --- probe -----------------------------------------------------------------------------


def test_probe_reports_docker_missing_without_running_anything(monkeypatch):
    monkeypatch.setattr(dockerctl, "docker_exe", lambda: None)
    state = dockerctl.probe()
    assert state.installed is False
    assert state.available is False
    assert "PATH" in state.reason


def test_probe_separates_installed_from_engine_up(fake_docker):
    _, install = fake_docker
    install(lambda argv: _fail("Cannot connect to the Docker daemon"))
    state = dockerctl.probe()
    assert state.installed is True
    assert state.engine_up is False
    assert state.available is False
    assert "daemon" in state.reason


def test_probe_reads_the_container_state_from_docker(fake_docker):
    _, install = fake_docker

    def responder(argv):
        if argv[1] == "inspect":
            return _ok("running\n")
        return _ok("27.0.3")

    install(responder)
    state = dockerctl.probe()
    assert state.available is True
    assert state.container == "running"
    assert state.running is True
    assert state.exists is True


def test_an_absent_container_is_none_not_an_error(fake_docker):
    _, install = fake_docker
    install(lambda argv: _fail("No such object") if argv[1] == "inspect" else _ok("27.0.3"))
    state = dockerctl.probe()
    assert state.available is True, "a never-created container must not disable the controls"
    assert state.container is None
    assert state.running is False
    assert state.exists is False


def test_probe_inspects_the_compose_containers_fixed_name(fake_docker):
    calls, install = fake_docker
    install(lambda argv: _ok("exited") if argv[1] == "inspect" else _ok("27.0.3"))
    dockerctl.probe()
    inspect = next(c for c in calls if c[1] == "inspect")
    assert inspect[-1] == dockerctl.CONTAINER_NAME


def test_missing_compose_plugin_is_its_own_sentence(fake_docker):
    _, install = fake_docker

    def responder(argv):
        if argv[1:3] == ["compose", "version"]:
            return _fail("unknown command")
        if argv[1] == "inspect":
            return _fail("No such object")
        return _ok("27.0.3")

    install(responder)
    state = dockerctl.probe()
    assert state.engine_up is True
    assert state.compose_available is False
    assert state.available is False
    assert "compose" in state.reason


# --- actions ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "verb"),
    [("start", "up"), ("restart", "restart"), ("stop", "stop"), ("rebuild", "up")],
)
def test_each_action_targets_the_checked_in_compose_file_and_service(fake_docker, action, verb):
    calls, install = fake_docker
    install(lambda argv: _ok("done"))
    dockerctl.run_action(action)
    (argv,) = calls
    assert argv[1] == "compose"
    assert argv[2] == "-f"
    assert argv[3] == str(dockerctl.COMPOSE_FILE)
    assert verb in argv
    assert argv[-1] == dockerctl.SERVICE


def test_stop_never_removes_the_container(fake_docker):
    """`down` would delete it, costing the next Start a full re-create and erasing the
    'exited' state the panel uses to decide Restart is meaningful."""
    calls, install = fake_docker
    install(lambda argv: _ok())
    dockerctl.run_action("stop")
    assert "down" not in calls[0]
    assert "stop" in calls[0]


def test_rebuild_forces_a_pull(fake_docker):
    """Without --pull always this is `up -d` on a cached image: an expensive no-op."""
    calls, install = fake_docker
    install(lambda argv: _ok())
    dockerctl.run_action("rebuild")
    assert ["--pull", "always"] == calls[0][calls[0].index("--pull") : calls[0].index("--pull") + 2]
    assert "--force-recreate" in calls[0]


def test_start_does_not_force_recreate(fake_docker):
    calls, install = fake_docker
    install(lambda argv: _ok())
    dockerctl.run_action("start")
    assert "--force-recreate" not in calls[0]
    assert "--pull" not in calls[0]


def test_a_failed_action_returns_the_output_instead_of_raising(fake_docker):
    _, install = fake_docker
    install(lambda argv: _fail("Error response from daemon: port is already allocated", code=1))
    outcome = dockerctl.run_action("start")
    assert outcome.ok is False
    assert outcome.code == 1
    assert "already allocated" in outcome.output


def test_action_output_is_trimmed_to_a_readable_tail(fake_docker):
    _, install = fake_docker
    install(lambda argv: _ok("\n".join(f"line {i}" for i in range(40))))
    outcome = dockerctl.run_action("start")
    assert outcome.output.splitlines()[0] == "line 28"
    assert len(outcome.output.splitlines()) == 12


def test_run_action_without_docker_is_an_outcome_not_a_crash(monkeypatch):
    monkeypatch.setattr(dockerctl, "docker_exe", lambda: None)
    outcome = dockerctl.run_action("start")
    assert outcome.ok is False
    assert "PATH" in outcome.output


# --- _run's own failure handling ---------------------------------------------------------


def test_run_turns_a_missing_binary_into_an_outcome():
    outcome = dockerctl._run(["archivenetwork-no-such-binary", "info"], 5.0)
    assert outcome.ok is False
    assert outcome.code == 127


def test_run_turns_a_timeout_into_an_outcome(monkeypatch):
    def explode(*a, **k):
        raise subprocess.TimeoutExpired(cmd="docker", timeout=1)

    monkeypatch.setattr(subprocess, "run", explode)
    outcome = dockerctl._run(["docker", "compose", "up"], 240.0)
    assert outcome.ok is False
    assert outcome.code == 124
    assert "240s" in outcome.output
