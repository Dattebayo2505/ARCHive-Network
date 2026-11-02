"""The Dev panel's item browser names its columns by hand — pin them to what the loader writes.

`GET /api/dev/rows` returns whole items, but `DevPanel.svelte` renders a *curated* subset in a
chosen order, because a media item carries a dozen attributes and showing them all is unreadable.
That curation is the weak point: an attribute name the loader never writes does not error, it
silently renders `—` forever.

That is exactly what the Postgres-era caption move broke: the album column was renamed, the panel
kept asking for the old name, and the caption was nowhere on screen while the API returned it.
`items.py` is the single home of the attributes the loader writes, so the panel is checked
against it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from archivenetwork.loader import items

PANEL = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "lib"
    / "components"
    / "DevPanel.svelte"
)

WRITTEN = {
    "media": {"id"} | items.MEDIA_REFRESH | items.MEDIA_SET_ONCE,
    "album": {"id"} | items.ALBUM_REFRESH | items.ALBUM_SET_ONCE,
}


def _curated_columns() -> dict[str, list[str]]:
    """The two literal arrays from the `columns` $derived, keyed by item type."""
    source = PANEL.read_text(encoding="utf-8")
    block = re.search(
        r"const columns = \$derived\(\s*table === 'media'\s*\?\s*(\[[^\]]*\])\s*:\s*(\[[^\]]*\])",
        source,
    )
    assert block, (
        "Could not find the `columns` $derived in DevPanel.svelte. If it was refactored, update "
        "this test to match — do not delete it; it is the only thing tying the panel to the items."
    )
    # The arrays are single-quoted JS string literals, which parse as Python literals unchanged.
    return {
        "media": ast.literal_eval(block.group(1)),
        "album": ast.literal_eval(block.group(2)),
    }


@pytest.mark.parametrize("kind", ["media", "album"])
def test_dev_panel_only_names_attributes_the_loader_writes(kind: str):
    missing = [c for c in _curated_columns()[kind] if c not in WRITTEN[kind]]
    assert not missing, (
        f"DevPanel.svelte asks for {missing} on {kind} items, which the loader never writes — "
        f"those cells will render as '—'. Written attributes: {sorted(WRITTEN[kind])}"
    )


def test_dev_panel_shows_the_album_description():
    """The specific regression: the album's caption must be on screen, not just in the payload."""
    assert "description" in _curated_columns()["album"]
