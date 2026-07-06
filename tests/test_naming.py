from streamlinify.inventory.naming import display_name


def test_derives_name_and_drops_random_suffix():
    assert (
        display_name("facebook-ArchersNetwork-2026-07-03-7xOuGnNl")
        == "Archers Network Facebook Export | 2026-07-03"
    )


def test_drops_trailing_annotation_after_suffix():
    assert (
        display_name("facebook-ArchersNetwork-2026-06-08-Th2bzEER_previous-week-posts")
        == "Archers Network Facebook Export | 2026-06-08"
    )


def test_falls_back_to_raw_name_when_no_date():
    assert display_name("export") == "export"
    assert display_name("some-random-folder") == "some-random-folder"


def test_splits_multiword_camelcase_page_name():
    assert (
        display_name("facebook-SomeLongPageName-2026-01-02-abc")
        == "Some Long Page Name Facebook Export | 2026-01-02"
    )
