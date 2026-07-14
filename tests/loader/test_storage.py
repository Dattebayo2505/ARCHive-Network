from pathlib import Path

from archivenetwork.loader.storage import LocalStorage, media_key


def test_key_is_grouped_by_hashtag_then_album():
    key = media_key("999", "ARCHEVT", "animusika-2026", ".jpg")
    assert key == "fb-exports/archevt/animusika-2026/999.jpg"


def test_video_posters_land_in_the_videos_group():
    assert media_key("v01", "ARCHENT", "videos", ".jpg") == "fb-exports/archent/videos/v01.jpg"


def test_media_without_a_canonical_tag_lands_in_uncategorized():
    assert media_key("v01", None, "videos", ".jpg") == "fb-exports/uncategorized/videos/v01.jpg"
    assert (
        media_key("s01", None, "unanchored", ".jpg")
        == "fb-exports/uncategorized/unanchored/s01.jpg"
    )


def test_key_preserves_the_source_suffix():
    assert media_key("999", "ARCHEVT", "animo-fest", ".png").endswith("/999.png")


def test_put_copies_then_is_idempotent(tmp_path: Path):
    src = tmp_path / "a.jpg"
    src.write_bytes(b"BYTES")
    store = LocalStorage(tmp_path / "store")
    key = store.key_for("999", "ARCHEVT", "animo-fest", ".jpg")

    assert store.exists(key) is False
    assert store.put(src, key) is True  # stored
    assert (store.root / key).read_bytes() == b"BYTES"
    assert store.exists(key) is True
    assert store.put(src, key) is False  # already there -> no re-upload
