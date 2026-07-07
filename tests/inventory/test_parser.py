from pathlib import Path

from archivenetwork.inventory.parser import (
    album_id_from_uri,
    build_inventory,
    photo_fbid,
    resolve_uri,
)

PREFIX = "this_profile's_activity_across_facebook"


def test_helpers(export_root: Path):
    uri = f"{PREFIX}/posts/media/AnimoFest_111/a01.jpg"
    assert photo_fbid(uri) == "a01"
    assert album_id_from_uri(uri) == "111"
    assert resolve_uri(uri, export_root) == export_root / "posts/media/AnimoFest_111/a01.jpg"


def test_build_inventory(export_root: Path):
    inv = build_inventory(export_root)

    by_id = {a.fb_album_id: a for a in inv.albums}
    assert set(by_id) == {"111", "222", "__non_album__"}
    assert by_id["111"].name == "Animo Fest"
    assert len(by_id["111"].photos) == 12
    assert by_id["222"].name == "Café Night"  # mojibake decoded

    # caption hoisted from the post body onto the album and removed from photos
    assert by_id["111"].description == "Great game today! #ARCH #Animo"
    a01 = next(p for p in by_id["111"].photos if p.fbid == "a01")
    assert a01.caption is None

    # non-album photos: m01 (present) and m02 (orphan)
    nonalbum = {p.fbid: p for p in by_id["__non_album__"].photos}
    assert set(nonalbum) == {"m01", "m02"}
    assert nonalbum["m01"].exists is True
    assert nonalbum["m02"].exists is False
    assert nonalbum["m01"].album_fbid == "__non_album__"


def test_build_inventory_groups_captions(grouping_export_root: Path):
    inv = build_inventory(grouping_export_root)
    by_id = {a.fb_album_id: a for a in inv.albums}

    # archive still runs first
    assert {p.fbid for p in inv.archived_photos} == {"t01"}

    # special album replaced by its derived caption-albums
    assert "777" not in by_id
    assert by_id["g01"].name == "HEADLINE ONE"
    assert by_id["g01"].origin == "Mobile uploads"
    assert by_id["g01"].uncapped is True
    assert by_id["g01"].media_slug == "HEADLINEONE_g01"
    assert {p.fbid for p in by_id["g01"].photos} == {"g01", "g02"}
    assert by_id["g01"].photos[0].ready_uri == "posts/media/HEADLINEONE_g01/g01.jpg"
    assert {p.fbid for p in by_id["g03"].photos} == {"g03", "g04", "g05"}

    # singleton + no-caption → unanchored non-album photos in __non_album__ album
    na = {p.fbid: p for p in by_id["__non_album__"].photos}
    assert set(na) == {"s01", "n01"}
    assert na["s01"].album_fbid == "__non_album__"
    assert na["s01"].ready_uri == "posts/media/s01.jpg"

    # non-special album with the same caption stays capped and untouched
    assert by_id["111"].uncapped is False
    assert {p.fbid for p in by_id["111"].photos} == {"a01"}
