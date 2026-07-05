from __future__ import annotations

import re

from .models import ExportInventory, Photo

# Albums the publication uses as photo dumps rather than themed sets. Matched by
# normalized name (strip + casefold) because an album's fb id is not knowable ahead
# of time. Update this set if Facebook renames these albums in a future export.
SPECIAL_ALBUM_NAMES = frozenset({"mobile uploads", "photos"})

# News-post caption tags. Ordered longest-phrase-first so a multi-word tag is tested
# before any shorter tag it could share a prefix with (defensive; no overlap today).
ARCHIVE_KEYWORDS: tuple[str, ...] = (
    "HAPPENING NOW",
    "REST IN PEACE",
    "JUST IN",
    "BREAKING",
    "COURTESY",
    "UPDATE",
    "WATCH",
    "LOOK",
)

# Leading emoji / whitespace / punctuation before the tag (e.g. "🚨 LOOK: ...").
_LEADING_NOISE = re.compile(r"^[^A-Za-z]+")


def is_special_album(name: str | None) -> bool:
    return (name or "").strip().casefold() in SPECIAL_ALBUM_NAMES


def archive_tag(caption: str | None) -> str | None:
    """Return the news tag a caption leads with, or None.

    Case-sensitive (tags are UPPERCASE by convention) and whole-word: the keyword
    must sit at the start (after leading emoji/space/punct) and be followed by a
    non-letter or end-of-string — so LOOKING / UPDATED / "Look at" never match.
    """
    if not caption:
        return None
    head = _LEADING_NOISE.sub("", caption)
    for kw in ARCHIVE_KEYWORDS:
        if head.startswith(kw):
            rest = head[len(kw):]
            if not rest or not rest[0].isalpha():
                return kw
    return None


def partition_archive(inventory: ExportInventory) -> None:
    """Move news-tagged photos out of the two special albums into `archived_photos`.

    Mutates in place: each special album is marked `uncapped` and keeps only its
    non-tagged photos; a tagged photo gets `archived=True` + its tag and moves to
    `inventory.archived_photos`. Non-special albums are untouched. Order preserved.
    """
    for album in inventory.albums:
        if not is_special_album(album.name):
            continue
        album.uncapped = True
        kept: list[Photo] = []
        for photo in album.photos:
            tag = archive_tag(photo.caption)
            if tag is None:
                kept.append(photo)
            else:
                photo.archived = True
                photo.archive_tag = tag
                inventory.archived_photos.append(photo)
        album.photos = kept
