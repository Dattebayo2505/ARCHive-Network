"""Fill the selection automatically — a dev convenience, not a curation shortcut.

**This does not reintroduce auto-keep.** The build still ships *exactly*
`selection.selected_fbids()`; the only thing that changes is who made the picks. Auto-curate
writes explicit, visible, editable choices into `selection.json` — every one of them shows up
in the gallery and can be changed. Auto-keep meant photos shipped *without ever being chosen*,
which is the thing the regression tests exist to prevent. Keep that distinction intact.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..inventory.models import ExportInventory
from .state import SelectionState


@dataclass
class AlbumPick:
    fb_album_id: str
    name: str
    picked: int
    available: int


@dataclass
class CurateResult:
    photos_selected: int = 0
    videos_selected: int = 0
    albums: list[AlbumPick] = field(default_factory=list)


def auto_curate(
    inventory: ExportInventory,
    selection: SelectionState,
    per_album: int,
    seed: int | None = None,
) -> CurateResult:
    """Pick up to `per_album` photos at random from every album, and select every video.

    An album with fewer than `per_album` usable photos contributes all of them. Orphans (a uri
    with no file on disk) are never picked — they cannot be built.

    Videos are uncapped and all are selected: the gallery seeds a first-frame still for each on
    load, so they are build-ready. Any that somehow still lack a still are reported by the build
    under `skipped_videos` rather than shipping silently.

    Archived photos and archived albums are absent from `inventory.albums`, so they can't be
    picked here — the same exclusion the builder enforces.

    The whole selection is **replaced**, not merged, in one atomic write.
    """
    rng = random.Random(seed)
    result = CurateResult()
    selections: dict[str, list[str]] = {}

    for album in inventory.albums:
        usable = [p for p in album.photos if p.exists and not p.is_video]
        n = min(per_album, len(usable))
        picked = rng.sample(usable, n) if n else []
        selections[album.fb_album_id] = [p.fbid for p in picked]
        result.photos_selected += len(picked)
        result.albums.append(
            AlbumPick(
                fb_album_id=album.fb_album_id,
                name=album.name,
                picked=len(picked),
                available=len(usable),
            )
        )

    videos = [v for v in inventory.videos if v.exists]
    selections["__videos__"] = [v.fbid for v in videos]
    result.videos_selected = len(videos)

    selection.replace_all(selections)
    return result
