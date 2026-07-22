from __future__ import annotations

import json
from pathlib import Path

from .policy import CapExceeded, NotSelectable, SelectionPolicy


class SelectionState:
    def __init__(self, path: Path, policy: SelectionPolicy) -> None:
        self.path = path
        self.policy = policy
        self._selected: dict[str, list[str]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._selected = {k: list(v) for k, v in data.items()}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: list(v) for k, v in self._selected.items() if v}
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def toggle(self, album_fbid: str, photo_fbid: str) -> bool:
        sel = self._selected.setdefault(album_fbid, [])
        if photo_fbid in sel:
            # Removal is always allowed — including from a disregarded album, so a
            # selection.json written before the album was disregarded can be cleaned up.
            sel.remove(photo_fbid)
            self._save()
            return False
        if self.policy.is_disregarded(album_fbid):
            raise NotSelectable(album_fbid)
        if not self.policy.can_select(album_fbid, len(sel)):
            raise CapExceeded(album_fbid)
        sel.append(photo_fbid)
        self._save()
        return True

    def replace_all(self, selections: dict[str, list[str]]) -> None:
        """Swap the entire selection in a single write.

        Deliberately atomic and total: anything absent from `selections` is dropped, so the
        caller's mapping *is* the new selection. Used by auto-curate, which replaces rather
        than merges — a half-applied selection would be worse than either outcome.
        """
        self._selected = {k: list(v) for k, v in selections.items() if v}
        self._save()

    def deselect_all(self, album_fbid: str) -> None:
        if album_fbid in self._selected:
            del self._selected[album_fbid]
            self._save()

    def truncate_to(self, album_fbid: str, max_count: int) -> list[str]:
        sel = self._selected.get(album_fbid, [])
        deselected = []
        if len(sel) > max_count:
            deselected = sel[max_count:]
            self._selected[album_fbid] = sel[:max_count]
            self._save()
        return deselected

    def is_selected(self, album_fbid: str, photo_fbid: str) -> bool:
        return photo_fbid in self._selected.get(album_fbid, [])

    def count(self, album_fbid: str) -> int:
        return len(self._selected.get(album_fbid, []))

    def selected_fbids(self) -> set[str]:
        out: set[str] = set()
        for fbids in self._selected.values():
            out |= set(fbids)
        return out
