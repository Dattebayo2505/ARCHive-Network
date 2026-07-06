from pathlib import Path

from streamlinify.web.registry import WorkspaceRegistry


def test_register_is_idempotent_on_id_and_sets_last_active(tmp_path: Path):
    reg = WorkspaceRegistry(tmp_path / "workspaces.json")
    root = tmp_path / "facebook-ArchersNetwork-2026-07-03-abc"
    root.mkdir()

    e1 = reg.register(root, managed=True, now=100.0)
    e2 = reg.register(root, managed=True, now=200.0)

    assert e1.id == "facebook-ArchersNetwork-2026-07-03-abc"
    assert e1.display_name == "Archers Network Facebook Export | 2026-07-03"
    assert len(reg.list()) == 1                # not duplicated
    assert e2.last_opened_ts == 200.0
    assert reg.last_active == e1.id


def test_list_sorted_by_last_opened_desc(tmp_path: Path):
    reg = WorkspaceRegistry(tmp_path / "workspaces.json")
    a = tmp_path / "facebook-A-2026-01-01-x"; a.mkdir()
    b = tmp_path / "facebook-B-2026-02-02-y"; b.mkdir()
    reg.register(a, managed=True, now=100.0)
    reg.register(b, managed=True, now=300.0)

    assert [e.id for e in reg.list()] == [b.name, a.name]


def test_remove_drops_entry_and_clears_last_active(tmp_path: Path):
    reg = WorkspaceRegistry(tmp_path / "workspaces.json")
    a = tmp_path / "facebook-A-2026-01-01-x"; a.mkdir()
    reg.register(a, managed=True, now=100.0)

    removed = reg.remove(a.name)
    assert removed is not None
    assert reg.get(a.name) is None
    assert reg.last_active is None


def test_persists_across_instances(tmp_path: Path):
    path = tmp_path / "workspaces.json"
    a = tmp_path / "facebook-A-2026-01-01-x"; a.mkdir()
    WorkspaceRegistry(path).register(a, managed=False, now=100.0)

    reloaded = WorkspaceRegistry(path)
    entry = reloaded.get(a.name)
    assert entry is not None
    assert entry.managed is False
    assert reloaded.last_active == a.name
