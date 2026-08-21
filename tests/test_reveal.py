from __future__ import annotations

from pathlib import Path

import pytest

from archivenetwork import reveal


def test_command_selects_file_on_windows(tmp_path: Path):
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")
    cmd = reveal.reveal_command(f, platform="win32")
    assert cmd == ["explorer", f"/select,{f}"]


def test_command_opens_dir_on_windows(tmp_path: Path):
    cmd = reveal.reveal_command(tmp_path, platform="win32")
    assert cmd == ["explorer", str(tmp_path)]


def test_command_reveals_file_on_macos(tmp_path: Path):
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")
    assert reveal.reveal_command(f, platform="darwin") == ["open", "-R", str(f)]


def test_command_opens_dir_on_macos(tmp_path: Path):
    assert reveal.reveal_command(tmp_path, platform="darwin") == ["open", str(tmp_path)]


def test_command_opens_containing_dir_on_linux(tmp_path: Path, monkeypatch):
    # No portable "select a file" flag on Linux → open the folder instead.
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.setattr(reveal.shutil, "which", lambda cmd: None)
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")
    assert reveal.reveal_command(f, platform="linux") == ["xdg-open", str(tmp_path)]


def test_command_uses_wslview_when_wslview_available_on_linux(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.setattr(
        reveal.shutil, "which", lambda cmd: "/usr/bin/wslview" if cmd == "wslview" else None
    )
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")
    assert reveal.reveal_command(f, platform="linux") == ["wslview", str(tmp_path)]


def test_command_uses_wslview_when_wsl_env_and_wslview_present(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.setattr(
        reveal.shutil, "which", lambda cmd: "/usr/bin/wslview" if cmd == "wslview" else None
    )
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")
    assert reveal.reveal_command(f, platform="linux") == ["wslview", str(tmp_path)]


def test_command_falls_back_to_xdg_open_in_wsl_without_wslview(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.setattr(reveal.shutil, "which", lambda cmd: None)
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")
    assert reveal.reveal_command(f, platform="linux") == ["xdg-open", str(tmp_path)]


def test_reveal_path_runs_command(tmp_path: Path, monkeypatch):
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")
    calls = []
    monkeypatch.setattr(reveal.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    reveal.reveal_path(f)
    assert calls
    if reveal.sys.platform.startswith("win"):
        # On Windows, reveal_path builds a hand-quoted string for /select,
        # because explorer.exe needs quotes only around the path after the
        # comma — not around the whole /select,path argument.
        assert calls[0] == f'explorer /select,"{f}"'
    else:
        assert calls[0] == reveal.reveal_command(f)


def test_reveal_path_missing_raises(tmp_path: Path):
    with pytest.raises(reveal.RevealError):
        reveal.reveal_path(tmp_path / "nope.jpg")

def test_command_uses_explorer_exe_in_wsl_when_wslview_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.setattr(
        reveal.shutil,
        "which",
        lambda cmd: "/mnt/c/Windows/explorer.exe" if cmd == "explorer.exe" else None,
    )
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")
    assert reveal.reveal_command(f, platform="linux") == ["explorer.exe", str(tmp_path)]


def test_command_uses_mnt_c_explorer_in_wsl_when_on_disk(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.setattr(reveal.shutil, "which", lambda cmd: None)
    monkeypatch.setattr(
        Path, "exists", lambda self: self.as_posix() == "/mnt/c/Windows/explorer.exe"
    )
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")
    assert reveal.reveal_command(f, platform="linux") == ["/mnt/c/Windows/explorer.exe", str(tmp_path)]


def test_reveal_path_raises_when_command_not_installed(tmp_path: Path, monkeypatch):
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")
    monkeypatch.setattr(reveal.shutil, "which", lambda cmd: None)
    with pytest.raises(
        reveal.RevealError,
        match=r"Cannot open file manager: command '.*' is not installed\.",
    ):
        reveal.reveal_path(f)
