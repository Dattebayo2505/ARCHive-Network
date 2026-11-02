"""items.py: the L / L1 ownership contract (Official-Schema §3.1-3.2, §5.2) as pure builders."""

from datetime import UTC, datetime, timedelta, timezone

from archivenetwork.loader.items import (
    ALBUM_REFRESH,
    ALBUM_SET_ONCE,
    CMS_OWNED,
    MEDIA_REFRESH,
    MEDIA_SET_ONCE,
    RETIRED,
    album_pk,
    album_update,
    iso_date,
    iso_utc,
    media_pk,
    media_update,
)
from archivenetwork.loader.read import AlbumRow, MediaRow

NOW = datetime(2026, 11, 2, 3, 4, 5, tzinfo=UTC)


def _album_row(**kw) -> AlbumRow:
    base = dict(
        fb_album_id="g01",
        title="HEADLINE ONE",
        caption="Body one.",
        date=datetime(2026, 7, 1, 9, 0, tzinfo=UTC),
        is_derived=True,
        hashtag="ARCHEVT",
        hashtags=["ARCHEVT", "ArchersNetwork"],
    )
    base.update(kw)
    return AlbumRow(**base)


def _photo_row(**kw) -> MediaRow:
    base = dict(
        fbid="g01",
        media_type="photo",
        fb_album_id="g01",
        title="G01",
        caption=None,
        uri="posts/media/HEADLINEONE_g01/g01.jpg",
        creation_at=datetime(2026, 7, 1, 9, 0, tzinfo=UTC),
        hashtag="ARCHEVT",
        hashtags=["ARCHEVT", "ArchersNetwork"],
        group="headline-one",
    )
    base.update(kw)
    return MediaRow(**base)


def _video_row(**kw) -> MediaRow:
    base = dict(
        fbid="v01",
        media_type="video",
        fb_album_id=None,
        title=None,
        caption="Watch this clip",
        uri="posts/media/videos/v01.jpg",
        creation_at=datetime(2026, 7, 2, 9, 0, tzinfo=UTC),
        hashtag="ARCHENT",
        hashtags=["ARCHENT"],
        group="videos",
    )
    base.update(kw)
    return MediaRow(**base)


def test_keys():
    assert album_pk("111") == "ALBUM#111" and media_pk("g01") == "MEDIA#g01"


def test_every_l_attribute_is_always_named_so_absent_ones_are_removed():
    u = media_update(_video_row(caption=None, fb_album_id=None), "fb-exports/x/v.jpg", "ws", NOW)
    assert set(u.refresh) == MEDIA_REFRESH and set(u.set_once) == MEDIA_SET_ONCE
    assert u.refresh["album_id"] is None and u.refresh["description"] is None


def test_album_update_matches_the_contract():
    u = album_update(_album_row(fb_album_id="111", is_derived=False), NOW)
    assert u.pk == "ALBUM#111" and set(u.refresh) == ALBUM_REFRESH
    assert set(u.set_once) == ALBUM_SET_ONCE
    assert u.set_once == {
        "id": "111",
        "kind": "photo",
        "source": "fb_export",
        "created_at": "2026-11-02T03:04:05Z",
    }
    assert u.refresh["loaded_at"] == "2026-11-02T03:04:05Z"
    assert u.refresh["date"] == "2026-07-01"
    assert u.refresh["hashtags"] == ["ARCHEVT", "ArchersNetwork"]


def test_a_derived_album_is_sourced_fb_export_derived():
    assert album_update(_album_row(is_derived=True), NOW).set_once["source"] == "fb_export_derived"


def test_album_caption_is_written_as_description():
    assert album_update(_album_row(caption="Body one."), NOW).refresh["description"] == "Body one."


def test_album_without_a_date_or_tags_removes_them():
    u = album_update(_album_row(date=None, hashtags=[], caption=None), NOW)
    assert u.refresh["date"] is None and u.refresh["hashtags"] is None
    assert u.refresh["description"] is None


def test_no_cms_or_retired_attribute_is_ever_written():
    for u in (album_update(_album_row(), NOW), media_update(_photo_row(), "k", "ws", NOW)):
        assert not (set(u.refresh) | set(u.set_once)) & (CMS_OWNED | RETIRED)


def test_media_carries_its_own_id_and_no_source():
    u = media_update(_photo_row(fbid="g01"), "k", "ws", NOW)
    assert u.pk == "MEDIA#g01" and u.set_once["id"] == "g01" and "source" not in u.set_once
    assert u.set_once["fbid"] == "g01" and u.set_once["storage_path"] == "k"
    assert u.refresh["source_workspace_id"] == "ws"


def test_anchored_media_partitions_by_album_and_sorts_by_creation_at():
    u = media_update(_photo_row(fb_album_id="g01", creation_at=NOW), "k", "ws", NOW)
    assert u.refresh["GSI1PK"] == "ALBUM#g01"
    assert u.refresh["GSI1SK"] == "2026-11-02T03:04:05Z"
    assert u.refresh["creation_at"] == "2026-11-02T03:04:05Z"


def test_anchored_media_reads_description_and_hashtags_from_its_album():
    u = media_update(_photo_row(fb_album_id="g01", hashtags=["ARCHEVT"]), "k", "ws", NOW)
    assert u.refresh["description"] is None and u.refresh["hashtags"] is None  # REMOVEd


def test_loose_media_carries_its_own_description_and_tags():
    u = media_update(_video_row(), "k", "ws", NOW)
    assert u.refresh["description"] == "Watch this clip"
    assert u.refresh["hashtags"] == ["ARCHENT"]
    assert u.refresh["album_id"] is None


def test_loose_media_partitions_by_its_canonical_tag_or_uncategorized():
    tagged = _video_row(hashtags=["ArchersAfterDark", "ARCHENT"])
    assert media_update(tagged, "k", "ws", NOW).refresh["GSI1PK"] == "LOOSE#ARCHENT"
    untagged = _video_row(hashtags=[])
    assert media_update(untagged, "k", "ws", NOW).refresh["GSI1PK"] == "LOOSE#uncategorized"


def test_media_without_creation_at_removes_gsi1sk():
    u = media_update(_photo_row(creation_at=None), "k", "ws", NOW)
    assert u.refresh["GSI1SK"] is None and u.refresh["creation_at"] is None


def test_empty_hashtags_are_removed_not_stored_empty():
    assert media_update(_video_row(hashtags=[]), "k", "ws", NOW).refresh["hashtags"] is None


def test_missing_title_is_removed():
    assert media_update(_photo_row(title=None), "k", "ws", NOW).refresh["title"] is None


def test_hashtag_lists_are_copied_not_shared():
    row = _album_row()
    u = album_update(row, NOW)
    assert u.refresh["hashtags"] == row.hashtags and u.refresh["hashtags"] is not row.hashtags


def test_iso_utc_converts_and_is_fixed_width():
    plus8 = timezone(timedelta(hours=8))
    assert iso_utc(datetime(2026, 1, 2, 11, 0, tzinfo=plus8)) == "2026-01-02T03:00:00Z"
    assert iso_utc(datetime(2026, 1, 2, 3, 0, 0, 999999, tzinfo=UTC)) == "2026-01-02T03:00:00Z"


def test_iso_date_is_the_utc_calendar_day():
    plus8 = timezone(timedelta(hours=8))
    assert iso_date(datetime(2026, 1, 2, 5, 0, tzinfo=plus8)) == "2026-01-01"
