from pathlib import Path

from streamlinify.inventory.parser import (
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
    assert set(by_id) == {"111", "222"}
    assert by_id["111"].name == "Animo Fest"
    assert len(by_id["111"].photos) == 12
    assert by_id["222"].name == "Café Night"  # mojibake decoded

    # caption hoisted from the post body onto album photos a01/a02
    a01 = next(p for p in by_id["111"].photos if p.fbid == "a01")
    assert a01.caption == "Great game today! #ARCH #Animo"

    # non-album photos: m01 (present) and m02 (orphan)
    nonalbum = {p.fbid: p for p in inv.non_album_photos}
    assert set(nonalbum) == {"m01", "m02"}
    assert nonalbum["m01"].exists is True
    assert nonalbum["m02"].exists is False
    assert nonalbum["m01"].album_fbid is None
