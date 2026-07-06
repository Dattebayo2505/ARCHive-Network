from pathlib import Path

from streamlinify.selection.archive_state import ArchiveState


def test_add_remove_roundtrip(tmp_path: Path):
    path = tmp_path / "archive.json"
    state = ArchiveState(path)
    assert state.archived_ids() == set()

    state.add("111")
    state.add("222")
    assert state.is_archived("111")
    assert state.archived_ids() == {"111", "222"}

    state.remove("111")
    assert not state.is_archived("111")
    assert state.archived_ids() == {"222"}


def test_persists_across_instances(tmp_path: Path):
    path = tmp_path / "archive.json"
    ArchiveState(path).add("333")

    assert ArchiveState(path).archived_ids() == {"333"}


def test_add_is_idempotent(tmp_path: Path):
    state = ArchiveState(tmp_path / "archive.json")
    state.add("111")
    state.add("111")
    assert state.archived_ids() == {"111"}
