from streamlinify.inventory.archive import archive_tag, is_special_album


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
