from pathlib import Path

import pytest

from archivenetwork.selection.policy import CapExceeded, DefaultPolicy, NotSelectable
from archivenetwork.selection.state import SelectionState


def test_toggle_and_count(tmp_path: Path):
    st = SelectionState(tmp_path / "sel.json", DefaultPolicy())
    assert st.toggle("111", "a01") is True
    assert st.is_selected("111", "a01") is True
    assert st.count("111") == 1
    assert st.toggle("111", "a01") is False  # toggled off
    assert st.count("111") == 0


def test_cap_enforced(tmp_path: Path):
    st = SelectionState(tmp_path / "sel.json", DefaultPolicy(max_per_album=2))
    st.toggle("111", "a01")
    st.toggle("111", "a02")
    with pytest.raises(CapExceeded):
        st.toggle("111", "a03")


def test_uncapped_album_accepts_more_than_the_cap(tmp_path: Path):
    """Derived caption-albums must never raise CapExceeded — they're leftover piles,
    not curated sets."""
    st = SelectionState(
        tmp_path / "sel.json",
        DefaultPolicy(max_per_album=2, uncapped_albums=frozenset({"g01"})),
    )
    for n in range(5):  # well past max_per_album=2
        assert st.toggle("g01", f"m{n:02d}") is True
    assert st.count("g01") == 5


def _disregarding(tmp_path: Path) -> SelectionState:
    return SelectionState(
        tmp_path / "sel.json",
        DefaultPolicy(disregarded_albums=frozenset({"__non_album__"})),
    )


def test_a_disregarded_album_refuses_a_pick(tmp_path: Path):
    st = _disregarding(tmp_path)
    with pytest.raises(NotSelectable):
        st.toggle("__non_album__", "m01")
    assert st.count("__non_album__") == 0


def test_a_disregarded_album_still_allows_removal(tmp_path: Path):
    """A selection.json written before the album was disregarded must be clearable.

    Refusing the toggle-off too would strand those picks in the file forever — visible in
    the counters, impossible to remove, and quietly dropped by the builder.
    """
    path = tmp_path / "sel.json"
    path.write_text('{"__non_album__": ["m01"]}', encoding="utf-8")
    st = _disregarding(tmp_path)

    assert st.toggle("__non_album__", "m01") is False
    assert st.count("__non_album__") == 0


def test_persistence_round_trip(tmp_path: Path):
    path = tmp_path / "sel.json"
    st = SelectionState(path, DefaultPolicy())
    st.toggle("111", "a01")
    st.toggle("222", "b01")

    reloaded = SelectionState(path, DefaultPolicy())
    assert reloaded.selected_fbids() == {"a01", "b01"}
