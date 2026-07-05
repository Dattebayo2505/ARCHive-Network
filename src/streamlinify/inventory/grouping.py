from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")


def caption_headline(caption: str) -> str:
    """The caption's first non-empty line, trimmed and truncated to 100 chars."""
    for line in caption.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:100]
    return caption.strip()[:100]


def media_slug(headline: str, synth_id: str) -> str:
    """`<AlnumHeadline≤30>_<synthId>` — the per-group media subdir name.

    The trailing `_<synthId>` mirrors FB's `<Album>_<albumFbid>` so the downstream
    ETL (and our own `album_id_from_uri`) recovers the synthetic id from the path.
    """
    alnum = _NON_ALNUM.sub("", headline)[:30] or "album"
    return f"{alnum}_{synth_id}"
