from archivenetwork.inventory.hashtags import (
    CANONICAL,
    canonical_tag,
    slugify,
    split_hashtags,
)


def test_canonical_is_the_six_section_tags():
    assert CANONICAL == (
        "ARCHEVT", "ARCHADS", "ARCHNEWS", "ARCHSPORTS", "ARCHCULTURE", "ARCHENT",
    )


def test_split_removes_tags_and_returns_them_in_written_order():
    text, tags = split_hashtags("Animusika 2026 was electric. #ARCHEVT #ArchersNetwork")
    assert text == "Animusika 2026 was electric."
    assert tags == ["ARCHEVT", "ArchersNetwork"]


def test_split_preserves_original_casing():
    _, tags = split_hashtags("Result is in. #ARCHNews")
    assert tags == ["ARCHNews"]


def test_split_tidies_whitespace_left_behind_by_a_mid_sentence_tag():
    text, tags = split_hashtags("The #ARCHEVT show goes on")
    assert text == "The show goes on"
    assert tags == ["ARCHEVT"]


def test_split_of_a_tags_only_caption_yields_no_prose():
    text, tags = split_hashtags("#ARCHEVT #ARCH")
    assert text is None
    assert tags == ["ARCHEVT", "ARCH"]


def test_split_of_untagged_text_is_a_passthrough():
    assert split_hashtags("Just a caption.") == ("Just a caption.", [])


def test_split_of_none_is_none():
    assert split_hashtags(None) == (None, [])


def test_canonical_tag_matches_case_insensitively_and_returns_uppercase():
    assert canonical_tag(["ArchersNetwork", "archnews"]) == "ARCHNEWS"


def test_canonical_tag_is_none_when_no_section_tag_is_present():
    assert canonical_tag(["ARCH", "Animo"]) is None


def test_canonical_tag_takes_the_first_match_when_convention_is_broken():
    assert canonical_tag(["ARCHENT", "ARCHEVT"]) == "ARCHENT"


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Animusika 2026") == "animusika-2026"


def test_slugify_drops_emoji_and_punctuation():
    assert slugify("THE PULSE OF MUSIC 🎶🎤") == "the-pulse-of-music"


def test_slugify_truncates_to_60_chars_without_a_trailing_hyphen():
    out = slugify("word " * 40)
    assert len(out) <= 60
    assert not out.endswith("-")


def test_slugify_of_unsluggable_input_is_empty():
    assert slugify("🎶🎤") == ""
