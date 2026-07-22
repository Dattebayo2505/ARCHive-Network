from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Callable

from ..config import settings


class CapExceeded(Exception):
    def __init__(self, album_fbid: str) -> None:
        super().__init__(f"album {album_fbid} is at its selection cap")
        self.album_fbid = album_fbid


class NotSelectable(Exception):
    """The album is disregarded — nothing in it may be picked, at any count.

    Distinct from `CapExceeded` on purpose: "full" is a state the volunteer can undo by
    deselecting something, "disregarded" is not, and the UI must not offer a swap.
    """

    def __init__(self, album_fbid: str) -> None:
        super().__init__(f"album {album_fbid} cannot be part of the ready folder")
        self.album_fbid = album_fbid


class SelectionPolicy(Protocol):
    def can_select(self, album_fbid: str, current_count: int) -> bool: ...

    def is_disregarded(self, album_fbid: str) -> bool: ...


@dataclass
class DefaultPolicy:
    """Per-album selection cap. Nothing is ever auto-kept.

    Every photo and video that reaches the build is one the user explicitly picked —
    videos live under `__videos__`. This policy only decides *how many* may be picked,
    never what ships by default.

    Albums in `uncapped_albums` have no cap; `__videos__` is likewise uncapped. A
    per-album override from `limits.json` (via `get_limit`) beats `max_per_album`.

    Albums in `disregarded_albums` (the synthetic `__non_album__` bucket) can never be
    picked from at all — a photo that belongs to no album has no slot in the ready folder,
    so offering it as a choice would be a promise the builder cannot keep.
    """

    max_per_album: int = settings.max_per_album
    uncapped_albums: frozenset[str] = frozenset()
    disregarded_albums: frozenset[str] = frozenset()
    get_limit: Callable[[str, int], int] | None = None

    def is_disregarded(self, album_fbid: str) -> bool:
        return album_fbid in self.disregarded_albums

    def can_select(self, album_fbid: str, current_count: int) -> bool:
        if self.is_disregarded(album_fbid):
            return False
        if album_fbid in self.uncapped_albums or album_fbid == "__videos__":
            return True
        limit = self.get_limit(album_fbid, self.max_per_album) if self.get_limit else self.max_per_album
        return current_count < limit
