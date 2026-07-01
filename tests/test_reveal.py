from __future__ import annotations

from pathlib import Path

import pytest

from streamlinify import reveal


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


def test_command_opens_containing_dir_on_linux(tmp_path: Path):
    # No portable "select a file" flag on Linux → open the folder instead.
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")
    assert reveal.reveal_command(f, platform="linux") == ["xdg-open", str(tmp_path)]


def test_reveal_path_runs_command(tmp_path: Path, monkeypatch):
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")
    calls: list[list[str]] = []
    monkeypatch.setattr(reveal.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    reveal.reveal_path(f)
    assert calls and calls[0] == reveal.reveal_command(f)


def test_reveal_path_missing_raises(tmp_path: Path):
    with pytest.raises(reveal.RevealError):
        reveal.reveal_path(tmp_path / "nope.jpg")
