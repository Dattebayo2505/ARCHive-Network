from pathlib import Path

from archivenetwork.ingest.validate import find_export_root, validate_export


def test_valid_export(export_root: Path):
    report = validate_export(export_root)
    assert report.ok is True
    assert report.missing == []


def test_missing_pieces(tmp_path: Path):
    report = validate_export(tmp_path)
    assert report.ok is False
    assert "posts/profile_posts_1.json" in report.missing


def test_find_export_root_descends(export_root: Path):
    parent = export_root.parent  # contains the "export" subfolder
    assert find_export_root(parent) == export_root
