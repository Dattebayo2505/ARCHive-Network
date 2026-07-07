from archivenetwork.inventory.archive import archive_tag, is_special_album


def test_is_special_album_normalizes_name():
    assert is_special_album("Mobile uploads") is True
    assert is_special_album("  PHOTOS  ") is True
    assert is_special_album("Photos") is True
    assert is_special_album("Animo Fest") is False
    assert is_special_album(None) is False


def test_archive_tag_matches_uppercase_prefix():
    assert archive_tag("BREAKING: Fire on campus") == "BREAKING"
    assert archive_tag("🚨 LOOK: Long lines today") == "LOOK"
    assert archive_tag("HAPPENING NOW: Gates open") == "HAPPENING NOW"
    assert archive_tag("JUST IN: Results are out") == "JUST IN"
    assert archive_tag("REST IN PEACE.") == "REST IN PEACE"
    assert archive_tag("COURTESY: Photo desk") == "COURTESY"
    assert archive_tag("WATCH: highlights") == "WATCH"
    assert archive_tag("UPDATE: schedule changed") == "UPDATE"


def test_archive_tag_rejects_non_tags():
    assert archive_tag("Look at this cute dog") is None
    assert archive_tag("We were watching the game") is None
    assert archive_tag("Updated our schedule") is None  # UPDATED != UPDATE (whole-word)
    assert archive_tag("LOOKING for volunteers") is None  # LOOKING != LOOK
    assert archive_tag("breaking: lowercase") is None  # case-sensitive
    assert archive_tag(None) is None
    assert archive_tag("") is None
    assert archive_tag("   ") is None


def test_partition_archive_sets_aside_tagged():
    from archivenetwork.inventory.archive import partition_archive
    from archivenetwork.inventory.models import Album, ExportInventory, Photo

    def p(fbid, caption, album):
        return Photo(fbid=fbid, original_uri="x", resolved_path="x", caption=caption, album_fbid=album)

    inv = ExportInventory(
        albums=[
            Album(fb_album_id="555", name="Mobile uploads",
                  photos=[p("u01", "BREAKING: x", "555"), p("u02", "hello", "555")]),
            Album(fb_album_id="111", name="Animo Fest", photos=[p("a01", "BREAKING: y", "111")]),
        ]
    )
    partition_archive(inv)

    by_id = {a.fb_album_id: a for a in inv.albums}
    assert by_id["555"].uncapped is True
    assert {x.fbid for x in by_id["555"].photos} == {"u02"}
    assert {x.fbid for x in inv.archived_photos} == {"u01"}
    # tag caption in a non-special album is left alone
    assert by_id["111"].uncapped is False
    assert {x.fbid for x in by_id["111"].photos} == {"a01"}
