"""Canonical Archers Network hashtags: extraction, matching, and slugs.

Pure functions only — no I/O, no state. Imported at the points where data leaves the
backend: `web/serializers.py` (the JSON API) and `loader/read.py` (the ETL). The ready
folder in between keeps its raw, hashtag-bearing captions, so it stays a faithful
FB-shaped mirror that can be re-read if these rules ever change.

`web/routes_gallery.py` is the one *inbound* caller: a volunteer edits an album caption as
clean prose, and `join_hashtags` — the exact inverse of `split_hashtags` — puts the tags
back before the override is stored. Editing prose can therefore never delete the canonical
section tag that routes an album's photos downstream.
"""

from __future__ import annotations

import re

# The six section tags. By editorial convention an album carries exactly one — but the
# convention is not enforced, so `canonical_tag` takes the first match and the UI shows
# every tag it found.
CANONICAL: tuple[str, ...] = (
    "ARCHEVT",
    "ARCHADS",
    "ARCHNEWS",
    "ARCHSPORTS",
    "ARCHCULTURE",
    "ARCHENT",
)

_CANONICAL_SET = {t.upper() for t in CANONICAL}
_HASHTAG = re.compile(r"#(\w+)", re.UNICODE)
_WHITESPACE = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def split_hashtags(text: str | None) -> tuple[str | None, list[str]]:
    """Split prose from hashtags. Returns (prose or None, tags in written order)."""
    if not text:
        return None, []
    tags = _HASHTAG.findall(text)
    prose = _HASHTAG.sub("", text)
    # Removing a mid-sentence tag leaves a double space; removing a trailing block of tags
    # leaves dangling blank lines. Tidy both, then trim.
    prose = _WHITESPACE.sub(" ", prose)
    prose = "\n".join(line.strip() for line in prose.splitlines())
    prose = _BLANK_LINES.sub("\n\n", prose).strip()
    return (prose or None), tags


def join_hashtags(prose: str | None, tags: list[str]) -> str | None:
    """Re-attach `tags` to `prose` as a trailing block. The inverse of `split_hashtags`.

    Round-trips: `join_hashtags(*split_hashtags(raw))` yields prose + tags in written order,
    normalised. Returns None only when there is neither prose nor a tag.
    """
    prose = (prose or "").strip()
    block = " ".join(f"#{t.lstrip('#')}" for t in tags)
    if prose and block:
        return f"{prose}\n\n{block}"
    return prose or block or None


def canonical_tag(tags: list[str]) -> str | None:
    """The first section tag among `tags`, uppercase. None when the album carries none."""
    for tag in tags:
        if tag.upper() in _CANONICAL_SET:
            return tag.upper()
    return None


def slugify(name: str) -> str:
    """A URL/CDN/shell-safe path segment: `THE PULSE OF MUSIC 🎶🎤` -> `the-pulse-of-music`."""
    slug = _NON_ALNUM.sub("-", name.lower()).strip("-")
    if len(slug) > 60:
        slug = slug[:60].rstrip("-")
    return slug
