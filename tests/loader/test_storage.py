from datetime import datetime, timezone
from pathlib import Path

from archivenetwork.loader.storage import LocalStorage, media_key


def _dt(y, m, d):
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


def test_key_is_date_partitioned_and_identity_named():
    assert media_key("999", _dt(2026, 6, 27), ".jpg") == "media/2026/06/27/999.jpg"


def test_key_falls_back_to_unknown_bucket_without_a_date():
    assert media_key("999", None, ".jpg") == "media/unknown/999.jpg"


def test_key_preserves_the_source_suffix():
    assert media_key("999", _dt(2026, 6, 27), ".png") == "media/2026/06/27/999.png"


def test_put_copies_then_is_idempotent(tmp_path: Path):
    src = tmp_path / "a.jpg"
    src.write_bytes(b"BYTES")
    store = LocalStorage(tmp_path / "store")
    key = store.key_for("999", _dt(2026, 6, 27), ".jpg")

    assert store.exists(key) is False
    assert store.put(src, key) is True  # stored
    assert (store.root / key).read_bytes() == b"BYTES"
    assert store.exists(key) is True
    assert store.put(src, key) is False  # already there -> no re-upload
