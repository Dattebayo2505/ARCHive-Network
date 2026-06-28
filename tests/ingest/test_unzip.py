import zipfile
from pathlib import Path

import pytest

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


def test_rejects_zip_slip(tmp_path: Path):
    zip_path = tmp_path / "evil.zip"
    _make_zip(zip_path, {"../evil.txt": "pwn"})
    with pytest.raises(ValueError):
        extract_zip(zip_path, tmp_path / "out")
