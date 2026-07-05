from pathlib import Path

from streamlinify.inventory.models import Album, ExportInventory, Photo


def _photo(fbid, album_fbid=None):
    return Photo(
        fbid=fbid,
        original_uri=f"exp/posts/media/x/{fbid}.jpg",
        resolved_path=Path(f"posts/media/x/{fbid}.jpg"),
        album_fbid=album_fbid,
    )


def test_is_non_album():
    assert _photo("a").is_non_album is True
    assert _photo("b", album_fbid="111").is_non_album is False


def test_lookup_helpers():
    inv = ExportInventory(
        albums=[Album(fb_album_id="111", name="A", photos=[_photo("p1", "111")])],
        non_album_photos=[_photo("p2")],
    )
    assert {p.fbid for p in inv.all_photos()} == {"p1", "p2"}
    assert inv.photo_by_fbid("p2").fbid == "p2"
    assert inv.photo_by_fbid("nope") is None


def test_all_photos_includes_archived():
    archived = _photo("z1", album_fbid="555")
    inv = ExportInventory(
        albums=[Album(fb_album_id="111", name="A", photos=[_photo("p1", "111")])],
        non_album_photos=[_photo("p2")],
        archived_photos=[archived],
    )
    assert {p.fbid for p in inv.all_photos()} == {"p1", "p2", "z1"}
    assert inv.photo_by_fbid("z1").fbid == "z1"


def test_photo_archive_defaults():
    p = _photo("p1", album_fbid="111")
    assert p.archived is False
    assert p.archive_tag is None
