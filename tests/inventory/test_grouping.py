from streamlinify.inventory.grouping import (
    caption_headline,
    derive_caption_albums,
    media_slug,
)
from streamlinify.inventory.models import Album, ExportInventory, Photo
from streamlinify.inventory.parser import album_id_from_uri


def test_caption_headline():
    assert caption_headline("HEADLINE ONE\n\nBody one.") == "HEADLINE ONE"
    assert caption_headline("  Solo line  ") == "Solo line"
    assert caption_headline("PEP-ARING 🔥\n\nHAPPENING NOW: x") == "PEP-ARING 🔥"
    assert caption_headline("x" * 150) == "x" * 100


def test_media_slug_shape_and_recoverable_id():
    assert media_slug("HEADLINE ONE", "g01") == "HEADLINEONE_g01"
    slug = media_slug("HEADLINE ONE", "999")
    assert album_id_from_uri(f"posts/media/{slug}/999.jpg") == "999"
    # headline with no alphanumerics falls back but keeps a recoverable id
    assert album_id_from_uri(f"posts/media/{media_slug('🔥', '42')}/42.jpg") == "42"


def _p(fbid, caption, album="777"):
    return Photo(
        fbid=fbid,
        original_uri=f"posts/media/Mobileuploads_777/{fbid}.jpg",
        resolved_path=f"posts/media/Mobileuploads_777/{fbid}.jpg",
        caption=caption,
        album_fbid=album,
    )


def test_derive_groups_unanchors_and_skips_normal_albums():
    special = Album(
        fb_album_id="777", name="Mobile uploads", uncapped=True,
        photos=[_p("g01", "H1\n\nb"), _p("g02", "H1\n\nb"), _p("s01", "Solo"), _p("n01", None)],
    )
    normal = Album(
        fb_album_id="111", name="Animo Fest",
        photos=[_p("a01", "H1\n\nb", "111")],
    )
    inv = ExportInventory(albums=[special, normal])
    derive_caption_albums(inv)

    by_id = {a.fb_album_id: a for a in inv.albums}
    # special album replaced by one derived album (the 2-photo group)
    assert "777" not in by_id
    assert by_id["g01"].name == "H1"
    assert by_id["g01"].origin == "Mobile uploads"
    assert by_id["g01"].uncapped is True
    assert by_id["g01"].media_slug == "H1_g01"
    assert {p.fbid for p in by_id["g01"].photos} == {"g01", "g02"}
    assert by_id["g01"].photos[0].album_fbid == "g01"
    assert by_id["g01"].photos[0].ready_uri == "posts/media/H1_g01/g01.jpg"

    # singleton + no-caption become unanchored non-album photos, then moved to the Non-Album album
    non_album_album = by_id["__non_album__"]
    na = {p.fbid: p for p in non_album_album.photos}
    assert set(na) == {"s01", "n01"}
    assert na["s01"].album_fbid == "__non_album__"
    assert na["s01"].ready_uri == "posts/media/s01.jpg"

    # a non-uncapped album with the same caption is left untouched
    assert by_id["111"].uncapped is False
    assert {p.fbid for p in by_id["111"].photos} == {"a01"}
