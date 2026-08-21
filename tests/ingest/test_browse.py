from pathlib import Path

import pytest

from archivenetwork.ingest.browse import available_roots, list_directory


def test_lists_only_subdirectories_sorted(tmp_path: Path):
    (tmp_path / "Beta").mkdir()
    (tmp_path / "alpha").mkdir()
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")

    result = list_directory(tmp_path)

    assert [d["name"] for d in result["dirs"]] == ["alpha", "Beta"]  # case-insensitive sort
    assert result["path"] == str(tmp_path.resolve())
    assert result["parent"] == str(tmp_path.resolve().parent)
    assert result["is_export"] is False


def test_hidden_directories_are_skipped(tmp_path: Path):
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible").mkdir()

    names = [d["name"] for d in list_directory(tmp_path)["dirs"]]

    assert names == ["visible"]


def test_lists_zip_files_only(tmp_path: Path):
    (tmp_path / "Beta.zip").write_bytes(b"PK")
    (tmp_path / "alpha.ZIP").write_bytes(b"PK")  # case-insensitive
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()

    result = list_directory(tmp_path)

    # Only zips, sorted case-insensitively; non-zip files excluded.
    assert [f["name"] for f in result["files"]] == ["alpha.ZIP", "Beta.zip"]
    assert result["files"][0]["path"] == str(tmp_path / "alpha.ZIP")
    # Directories stay in their own bucket.
    assert [d["name"] for d in result["dirs"]] == ["sub"]


def test_hidden_zip_files_are_skipped(tmp_path: Path):
    (tmp_path / ".secret.zip").write_bytes(b"PK")
    (tmp_path / "shown.zip").write_bytes(b"PK")

    names = [f["name"] for f in list_directory(tmp_path)["files"]]

    assert names == ["shown.zip"]


def test_flags_a_loadable_export(export_root: Path):
    # The export itself is loadable...
    assert list_directory(export_root)["is_export"] is True
    # ...and so is its parent, since ingest descends one level.
    parent = list_directory(export_root.parent)
    export_entry = next(d for d in parent["dirs"] if d["name"] == "export")
    assert export_entry["is_export"] is True


def test_none_defaults_to_home():
    assert list_directory(None)["path"] == str(Path.home().resolve())


def test_exposes_available_drive_roots(tmp_path: Path):
    result = list_directory(tmp_path)
    assert result["drives"]  # non-empty
    assert all(Path(d).exists() for d in result["drives"])


def test_available_roots_are_real_directories():
    roots = available_roots()
    assert roots
    assert all(Path(r).is_dir() for r in roots)


def test_available_roots_macos(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("archivenetwork.ingest.browse.os.name", "posix")
    monkeypatch.setattr("archivenetwork.ingest.browse.sys.platform", "darwin")
    monkeypatch.setattr(
        Path, "exists", lambda self: self.as_posix() in ("/", "/Volumes")
    )
    monkeypatch.setattr(
        Path, "is_dir", lambda self: self.as_posix() in ("/", "/Volumes")
    )
    assert available_roots() == ["/", "/Volumes"]


def test_available_roots_macos_no_volumes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("archivenetwork.ingest.browse.os.name", "posix")
    monkeypatch.setattr("archivenetwork.ingest.browse.sys.platform", "darwin")
    monkeypatch.setattr(Path, "exists", lambda self: self.as_posix() == "/")
    monkeypatch.setattr(Path, "is_dir", lambda self: self.as_posix() == "/")
    assert available_roots() == ["/"]


def test_available_roots_linux(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("archivenetwork.ingest.browse.os.name", "posix")
    monkeypatch.setattr("archivenetwork.ingest.browse.sys.platform", "linux")
    monkeypatch.delenv("USER", raising=False)
    monkeypatch.delenv("LOGNAME", raising=False)
    monkeypatch.setattr(
        Path, "exists", lambda self: self.as_posix() in ("/", "/media", "/mnt")
    )
    monkeypatch.setattr(
        Path, "is_dir", lambda self: self.as_posix() in ("/", "/media", "/mnt")
    )
    assert available_roots() == ["/", "/media", "/mnt"]


def test_available_roots_linux_partial_mounts(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("archivenetwork.ingest.browse.os.name", "posix")
    monkeypatch.setattr("archivenetwork.ingest.browse.sys.platform", "linux")
    monkeypatch.delenv("USER", raising=False)
    monkeypatch.delenv("LOGNAME", raising=False)
    monkeypatch.setattr(
        Path, "exists", lambda self: self.as_posix() in ("/", "/mnt")
    )
    monkeypatch.setattr(
        Path, "is_dir", lambda self: self.as_posix() in ("/", "/mnt")
    )
    assert available_roots() == ["/", "/mnt"]


def test_available_roots_linux_with_run_media(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("archivenetwork.ingest.browse.os.name", "posix")
    monkeypatch.setattr("archivenetwork.ingest.browse.sys.platform", "linux")
    monkeypatch.setenv("USER", "archiver")
    valid = {"/", "/media", "/mnt", "/run/media", "/run/media/archiver"}
    monkeypatch.setattr(Path, "exists", lambda self: self.as_posix() in valid)
    monkeypatch.setattr(Path, "is_dir", lambda self: self.as_posix() in valid)
    assert available_roots() == ["/", "/media", "/mnt", "/run/media", "/run/media/archiver"]


def test_available_roots_windows(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("archivenetwork.ingest.browse.os.name", "nt")
    monkeypatch.setattr(
        Path, "exists", lambda self: str(self) in ("C:\\", "D:\\")
    )
    monkeypatch.setattr(
        Path, "is_dir", lambda self: str(self) in ("C:\\", "D:\\")
    )
    assert available_roots() == ["C:\\", "D:\\"]


def test_missing_path_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        list_directory(tmp_path / "does-not-exist")


def test_file_path_raises(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        list_directory(f)
