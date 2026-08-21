import os
import stat
from pathlib import Path

from archivenetwork.fsops import remove_tree


def test_remove_tree_deletes_directory(tmp_path: Path):
    target = tmp_path / "subdir"
    target.mkdir()
    (target / "file.txt").write_text("hello", encoding="utf-8")
    assert target.exists()

    assert remove_tree(target) is True
    assert not target.exists()


def test_remove_tree_nonexistent_returns_true(tmp_path: Path):
    target = tmp_path / "nonexistent"
    assert remove_tree(target) is True


def test_remove_tree_handles_readonly_files(tmp_path: Path):
    target = tmp_path / "readonly_dir"
    target.mkdir()
    ro_file = target / "readonly.txt"
    ro_file.write_text("protected", encoding="utf-8")

    # Make file read-only (chmod 444 / S_IREAD)
    os.chmod(ro_file, stat.S_IREAD)

    nested = target / "nested"
    nested.mkdir()
    ro_nested_file = nested / "nested_readonly.txt"
    ro_nested_file.write_text("also protected", encoding="utf-8")
    os.chmod(ro_nested_file, stat.S_IREAD)

    assert target.exists()
    assert remove_tree(target) is True
    assert not target.exists()
