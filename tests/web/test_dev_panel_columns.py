"""The Dev panel's row browser names its columns by hand — pin them to the real schema.

`GET /api/dev/rows` is generic (`SELECT *`, columns read off `cur.description`), but
`DevPanel.svelte` renders a *curated* subset in a chosen order, because `media` has 13 columns
and showing them all is unreadable. That curation is the weak point: a hardcoded name that no
longer exists in Postgres does not error, it silently renders `—` forever.

That is exactly what the caption move broke. `photo_album.description` became `caption`, the
panel kept asking for `description`, and the album table showed a column of em-dashes with the
caption nowhere on screen — while the API had been returning it the whole time.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PANEL = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "lib"
    / "components"
    / "DevPanel.svelte"
)


def _curated_columns() -> dict[str, list[str]]:
    """The two literal arrays from the `columns` $derived, keyed by table."""
    source = PANEL.read_text(encoding="utf-8")
    block = re.search(
        r"const columns = \$derived\(\s*table === 'media'\s*\?\s*(\[[^\]]*\])\s*:\s*(\[[^\]]*\])",
        source,
    )
    assert block, (
        "Could not find the `columns` $derived in DevPanel.svelte. If it was refactored, update "
        "this test to match — do not delete it; it is the only thing tying the panel to the schema."
    )
    # The arrays are single-quoted JS string literals, which parse as Python literals unchanged.
    return {
        "media": ast.literal_eval(block.group(1)),
        "photo_album": ast.literal_eval(block.group(2)),
    }


@pytest.mark.parametrize("table", ["media", "photo_album"])
def test_dev_panel_only_names_columns_that_exist(pg_conn, table: str):
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        )
        actual = {r[0] for r in cur.fetchall()}

    assert actual, f"{table} was not created by the pg_conn fixture"
    missing = [c for c in _curated_columns()[table] if c not in actual]
    assert not missing, (
        f"DevPanel.svelte asks for {missing} on `{table}`, which the schema does not have — "
        f"those cells will render as '—'. Actual columns: {sorted(actual)}"
    )


def test_dev_panel_shows_the_album_caption(pg_conn):
    """The specific regression: the caption must be on screen, not just in the payload."""
    assert "caption" in _curated_columns()["photo_album"]
