from pathlib import Path

import pytest

from archivenetwork.selection.policy import CapExceeded, DefaultPolicy
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


def test_persistence_round_trip(tmp_path: Path):
    path = tmp_path / "sel.json"
    st = SelectionState(path, DefaultPolicy())
    st.toggle("111", "a01")
    st.toggle("222", "b01")

    reloaded = SelectionState(path, DefaultPolicy())
    assert reloaded.selected_fbids() == {"a01", "b01"}
