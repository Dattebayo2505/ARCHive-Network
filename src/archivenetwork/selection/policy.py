from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Callable

from ..config import settings


class CapExceeded(Exception):
    def __init__(self, album_fbid: str) -> None:
        super().__init__(f"album {album_fbid} is at its selection cap")
        self.album_fbid = album_fbid


class SelectionPolicy(Protocol):
    def can_select(self, album_fbid: str, current_count: int) -> bool: ...


@dataclass
class DefaultPolicy:
    """Per-album selection cap. Nothing is ever auto-kept.

    Every photo and video that reaches the build is one the user explicitly picked —
    including non-album photos (pickable under the synthetic `__non_album__` album) and
    videos (under `__videos__`). This policy only decides *how many* may be picked, never
    what ships by default.

    Albums in `uncapped_albums` have no cap; `__videos__` is likewise uncapped. A
    per-album override from `limits.json` (via `get_limit`) beats `max_per_album`.
    """

    max_per_album: int = settings.max_per_album
    uncapped_albums: frozenset[str] = frozenset()
    get_limit: Callable[[str, int], int] | None = None

    def can_select(self, album_fbid: str, current_count: int) -> bool:
        if album_fbid in self.uncapped_albums or album_fbid == "__videos__":
            return True
        limit = self.get_limit(album_fbid, self.max_per_album) if self.get_limit else self.max_per_album
        return current_count < limit
