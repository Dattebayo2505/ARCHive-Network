"""The Postgres fixtures must never target the database the app actually runs on.

`pg_conn` drops tables. It used to connect straight to `Settings().database_url`, so a plain
`pytest -q` wiped the dev database and left fixture rows (album `g01`/`HEADLINE ONE`, media
`g01..g05`) committed behind, pointing at a `tmp_path` store that pytest later deleted — the
Dev panel then served 404s for `/store/fb-exports/archevt/headline-one/g01.jpg`.
"""

import conftest
import pytest

from archivenetwork.loader import db


def _configured_url() -> str:
    from archivenetwork.config import Settings

    url = Settings().database_url
    if not url:
        pytest.skip("ARCHIVENETWORK_DATABASE_URL not set")
    return url


def test_scratch_url_never_points_at_the_configured_database():
    configured = _configured_url()
    scratch = conftest._scratch_url()

    assert db.database_name(scratch) != db.database_name(configured)
    assert db.database_name(scratch).endswith(conftest.TEST_DB_SUFFIX)


def test_scratch_url_keeps_the_configured_server_and_credentials():
    """Only the dbname may differ — otherwise the suite would skip instead of running."""
    from psycopg.conninfo import conninfo_to_dict

    configured = conninfo_to_dict(_configured_url())
    scratch = conninfo_to_dict(conftest._scratch_url())

    assert scratch.pop("dbname") != configured.pop("dbname")
    assert scratch == configured


def test_pg_conn_is_connected_to_the_scratch_database(pg_conn):
    assert db.database_name(pg_conn.info.dsn).endswith(conftest.TEST_DB_SUFFIX)


def test_pg_conn_starts_from_an_empty_schema(pg_conn):
    """Whatever a previous test committed, each test opens on a clean slate."""
    assert db.counts(pg_conn) == {"photo_album": 0, "media": 0}
