import zipfile
from pathlib import Path

import pytest

from streamlinify.config import settings
from streamlinify.ingest.unzip import extract_zip


def _make_zip(path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def test_extracts_files(tmp_path: Path):
    zip_path = tmp_path / "x.zip"
    _make_zip(zip_path, {"posts/profile_posts_1.json": "[]"})
    dest = tmp_path / "out"
    extract_zip(zip_path, dest)
    assert (dest / "posts" / "profile_posts_1.json").read_text() == "[]"


def test_extracts_nested_tree(tmp_path: Path):
    zip_path = tmp_path / "tree.zip"
    _make_zip(
        zip_path,
        {
            "posts/album/0.json": "{}",
            "posts/media/a/photo.jpg": "img",
        },
    )
    dest = tmp_path / "out"
    extract_zip(zip_path, dest)
    assert (dest / "posts" / "album" / "0.json").read_text() == "{}"
    assert (dest / "posts" / "media" / "a" / "photo.jpg").read_text() == "img"


def test_rejects_zip_slip(tmp_path: Path):
    zip_path = tmp_path / "evil.zip"
    _make_zip(zip_path, {"../evil.txt": "pwn"})
    with pytest.raises(ValueError):
        extract_zip(zip_path, tmp_path / "out")
    # The traversal target must never be written.
    assert not (tmp_path / "evil.txt").exists()


def test_falls_back_to_zipfile_when_no_7zip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # No configured binary and none discoverable on PATH -> stdlib zipfile fallback,
    # so extraction still succeeds on machines without 7-Zip (e.g. a bare macOS/Linux).
    zip_path = tmp_path / "x.zip"
    _make_zip(zip_path, {"posts/profile_posts_1.json": "[]"})
    monkeypatch.setattr(settings, "seven_zip_exe", None)
    monkeypatch.setattr("streamlinify.ingest.unzip.shutil.which", lambda _name: None)
    dest = tmp_path / "out"
    extract_zip(zip_path, dest)
    assert (dest / "posts" / "profile_posts_1.json").read_text() == "[]"


def test_windows_exe_ignored_off_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # A committed vendor/7za.exe "exists" on macOS/Linux but cannot run there, so
    # find_seven_zip must skip it (and fall through to PATH / zipfile) off Windows.
    from streamlinify.ingest.unzip import find_seven_zip

    fake_exe = tmp_path / "7za.exe"
    fake_exe.write_bytes(b"MZ")  # a stand-in Windows binary
    monkeypatch.setattr(settings, "seven_zip_exe", fake_exe)
    monkeypatch.setattr("streamlinify.ingest.unzip.shutil.which", lambda _name: None)
    monkeypatch.setattr("streamlinify.ingest.unzip.sys.platform", "linux")
    assert find_seven_zip() is None
