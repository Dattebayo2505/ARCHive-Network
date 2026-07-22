"""Create / drop / probe the *database itself*, not just its tables.

The lifecycle tests need a reachable server but deliberately do NOT use `pg_conn` — that
fixture connects to the configured database, which is the very thing under test here (it may
not exist yet). They operate on a throwaway `archivenetwork_probe_<n>` database instead and
never touch the configured one.
"""

from __future__ import annotations

import psycopg
import pytest

from archivenetwork.config import Settings
from archivenetwork.loader import db

# --- pure URL surgery: no server required -------------------------------------------------

URL = "postgresql://postgres:secret@127.0.0.1:5432/archivenetwork_dev"


def test_database_name_reads_the_dbname():
    assert db.database_name(URL) == "archivenetwork_dev"


def test_maintenance_url_swaps_the_dbname_and_keeps_the_server():
    maint = db.maintenance_url(URL)
    info = psycopg.conninfo.conninfo_to_dict(maint)
    assert info["dbname"] == "postgres"
    assert info["host"] == "127.0.0.1"
    assert info["port"] == "5432"
    assert info["user"] == "postgres"
    assert info["password"] == "secret"


def test_maintenance_url_of_the_maintenance_db_is_stable():
    maint = db.maintenance_url("postgresql://postgres@127.0.0.1:5432/postgres")
    assert psycopg.conninfo.conninfo_to_dict(maint)["dbname"] == "postgres"


# --- server-backed lifecycle --------------------------------------------------------------


@pytest.fixture
def server_url():
    """The configured URL, skipping unless its *server* is reachable.

    Unlike `pg_conn` this only needs the server, so it still runs when the configured
    database is missing — the exact state this feature exists to repair.
    """
    url = Settings().database_url
    if not url:
        pytest.skip("ARCHIVENETWORK_DATABASE_URL not set; skipping Postgres-backed test")
    probe = db.probe(url)
    if not probe.server_up:
        pytest.skip(f"Postgres unreachable, skipping: {probe.reason}")
    return url


@pytest.fixture
def scratch_url(server_url):
    """A URL for a throwaway database that is guaranteed absent before and after."""
    url = db.with_database(server_url, "archivenetwork_probe_db")
    db.drop_database(url)
    yield url
    db.drop_database(url)


def test_probe_reports_a_missing_database_without_claiming_the_server_is_down(scratch_url):
    result = db.probe(scratch_url)
    assert result.server_up is True
    assert result.database == "archivenetwork_probe_db"
    assert result.database_exists is False


def test_create_then_probe_then_drop(scratch_url):
    assert db.create_database(scratch_url) is True
    result = db.probe(scratch_url)
    assert result.server_up is True
    assert result.database_exists is True

    assert db.drop_database(scratch_url) is True
    assert db.probe(scratch_url).database_exists is False


def test_create_is_idempotent(scratch_url):
    assert db.create_database(scratch_url) is True
    # Already there: reported as "nothing to do", not raised.
    assert db.create_database(scratch_url) is False


def test_drop_is_idempotent(scratch_url):
    assert db.drop_database(scratch_url) is False


def test_a_created_database_can_hold_the_schema(scratch_url):
    db.create_database(scratch_url)
    with db.connect(scratch_url) as conn:
        db.create_tables(conn)
        assert db.tables_exist(conn) is True


def test_drop_survives_an_open_connection_to_the_target(scratch_url):
    """Postgres refuses DROP DATABASE while sessions are attached — drop must evict them."""
    db.create_database(scratch_url)
    conn = db.connect(scratch_url)
    try:
        assert db.drop_database(scratch_url) is True
    finally:
        conn.close()


def test_probe_reports_an_unreachable_server_rather_than_raising():
    # Port 1 is reserved and never listening.
    result = db.probe("postgresql://postgres@127.0.0.1:1/archivenetwork_dev")
    assert result.server_up is False
    assert result.database_exists is False
    assert result.reason
