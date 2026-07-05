from __future__ import annotations

import re

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
