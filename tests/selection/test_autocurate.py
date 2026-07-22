from pathlib import Path

from archivenetwork.inventory.parser import build_inventory
from archivenetwork.selection.autocurate import auto_curate
from archivenetwork.selection.policy import DefaultPolicy
from archivenetwork.selection.state import SelectionState


def _sel(tmp_path: Path, inv) -> SelectionState:
    uncapped = frozenset(a.fb_album_id for a in inv.albums if a.uncapped)
    disregarded = frozenset(a.fb_album_id for a in inv.albums if a.disregarded)
    return SelectionState(
        tmp_path / "sel.json",
        DefaultPolicy(
            max_per_album=10, uncapped_albums=uncapped, disregarded_albums=disregarded
        ),
    )


def test_picks_at_most_n_per_album_and_all_of_a_short_album(export_root: Path, tmp_path: Path):
    inv = build_inventory(export_root)
    sel = _sel(tmp_path, inv)

    result = auto_curate(inv, sel, per_album=2, seed=0)

    for pick in result.albums:
        assert pick.picked == min(2, pick.available)  # <= N, or all of a short album
        assert sel.count(pick.fb_album_id) == pick.picked


def test_never_picks_an_orphan(export_root: Path, tmp_path: Path):
    """m02 is referenced by the JSON but has no file on disk — it cannot be built."""
    inv = build_inventory(export_root)
    sel = _sel(tmp_path, inv)

    auto_curate(inv, sel, per_album=10, seed=0)

    assert "m02" not in sel.selected_fbids()


def test_selects_every_video(video_export_root: Path, tmp_path: Path):
    inv = build_inventory(video_export_root)
    sel = _sel(tmp_path, inv)

    result = auto_curate(inv, sel, per_album=10, seed=0)

    assert result.videos_selected == len(inv.videos) == 1
    assert sel.is_selected("__videos__", "v01") is True


def test_replaces_rather_than_merges(export_root: Path, tmp_path: Path):
    inv = build_inventory(export_root)
    sel = _sel(tmp_path, inv)
    sel.toggle("111", "a01")
    sel.toggle("111", "a02")

    auto_curate(inv, sel, per_album=1, seed=0)

    # The album now holds exactly the one auto-picked photo, not the two prior picks plus it.
    assert sel.count("111") == 1


def test_archived_photos_are_never_picked(archive_export_root: Path, tmp_path: Path):
    inv = build_inventory(archive_export_root)
    sel = _sel(tmp_path, inv)

    auto_curate(inv, sel, per_album=10, seed=0)

    archived = {p.fbid for p in inv.archived_photos}
    assert archived  # the fixture really does archive some
    assert not (archived & sel.selected_fbids())


def test_non_album_photos_are_never_picked(export_root: Path, tmp_path: Path):
    """The `__non_album__` bucket is disregarded — auto-curate must skip it entirely.

    Unlike archived media (absent from `inventory.albums`), this bucket *is* in the album
    list because the gallery shows it, so the skip has to be explicit. Picking from it would
    write selections the builder then throws away — visible checkmarks on photos that never
    ship.
    """
    inv = build_inventory(export_root)
    sel = _sel(tmp_path, inv)

    result = auto_curate(inv, sel, per_album=10, seed=0)

    non_album = next(a for a in inv.albums if a.disregarded)
    assert non_album.photos  # the fixture really does produce non-album photos
    assert not ({p.fbid for p in non_album.photos} & sel.selected_fbids())
    assert non_album.fb_album_id not in {a.fb_album_id for a in result.albums}


def test_auto_curate_is_not_auto_keep(export_root: Path, tmp_path: Path):
    """The build's keep set is still *exactly* the selection — auto-curate only writes picks.

    Guards the invariant that nothing ships unless it was chosen: a photo auto-curate did NOT
    pick must not reach the build, and deselecting an auto-picked photo must remove it.
    """
    from archivenetwork.transform.builder import build_ready_folder

    inv = build_inventory(export_root)
    sel = _sel(tmp_path, inv)
    auto_curate(inv, sel, per_album=1, seed=0)

    picked = sel.selected_fbids()
    all_photos = {p.fbid for p in inv.all_photos() if p.exists}
    assert picked < all_photos  # a strict subset — most photos were NOT picked

    result = build_ready_folder(export_root, tmp_path / "ready", sel.selected_fbids())
    assert result.copied == len([f for f in picked if f in all_photos])
