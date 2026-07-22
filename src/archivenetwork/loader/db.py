"""PostgreSQL connection and schema.

Only the two tables this ETL actually populates (PLAN §4). Taxonomy, contributors and users are
CMS-overlay concerns with no source in the export — `media` deliberately has **no
`category_id`**; the CMS adds that FK later. Pretending otherwise would defeat the point of
validating the schema against real data.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS photo_album (
    fb_album_id  text PRIMARY KEY,
    title        text NOT NULL,
    caption      text,          -- the post body every member photo shares (PLAN.md §3.1)
    date         timestamptz,
    hashtag      text,
    is_derived   boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS media (
    media_id            bigserial PRIMARY KEY,
    fbid                text NOT NULL UNIQUE,
    media_type          text NOT NULL CHECK (media_type IN ('photo', 'video')),
    fb_album_id         text REFERENCES photo_album(fb_album_id),
    title               text,
    caption             text,          -- an OVERRIDE: NULL whenever fb_album_id is set
    hashtag             text,
    storage_path        text NOT NULL,
    original_fb_uri     text,
    creation_at         timestamptz,
    source_workspace_id text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS media_album_idx ON media(fb_album_id);
CREATE INDEX IF NOT EXISTS media_type_idx  ON media(media_type);

-- Migration for a database created before the caption move. `CREATE TABLE IF NOT EXISTS` is a
-- no-op on an existing table, so without this an older dev DB keeps `photo_album.description`
-- and the INSERT below fails on a column that isn't there. RENAME (not ADD + DROP) so a
-- volunteer's edited caption survives the upgrade.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'photo_album' AND column_name = 'description')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'photo_album' AND column_name = 'caption') THEN
        ALTER TABLE photo_album RENAME COLUMN description TO caption;
    END IF;
END $$;
ALTER TABLE photo_album ADD COLUMN IF NOT EXISTS caption text;
ALTER TABLE photo_album DROP COLUMN IF EXISTS description;
-- `media.description` only ever duplicated `media.caption`; it is gone, not deprecated.
ALTER TABLE media DROP COLUMN IF EXISTS description;
"""

DROP_SQL = "DROP TABLE IF EXISTS media; DROP TABLE IF EXISTS photo_album;"


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(_bounded(database_url))


# --- Database-level admin -----------------------------------------------------------------
# `connect()` above needs the database to already exist. These talk to the *server* via the
# always-present `postgres` maintenance database, so they still work in the one state that
# matters here: the server is up but our database was never created.

MAINTENANCE_DB = "postgres"

# Every connection here backs a button in the Dev panel, so it must fail *fast* when nothing
# is listening. libpq's default is to wait on the OS TCP timeout — ~21s per address on Windows,
# long enough that the UI reads as hung rather than as "the server is down". This bounds only
# how long *establishing* a connection may take; queries on an open connection are unaffected.
CONNECT_TIMEOUT = 3


def _bounded(conninfo: str) -> str:
    """The same conninfo with a short connect timeout, unless the caller already set one."""
    info = conninfo_to_dict(conninfo)
    info.setdefault("connect_timeout", CONNECT_TIMEOUT)
    return make_conninfo(**info)


def with_database(database_url: str, dbname: str) -> str:
    """The same server/credentials, pointed at a different database."""
    info = conninfo_to_dict(database_url)
    info["dbname"] = dbname
    return make_conninfo(**info)


def database_name(database_url: str) -> str:
    return conninfo_to_dict(database_url).get("dbname") or ""


def maintenance_url(database_url: str) -> str:
    return with_database(database_url, MAINTENANCE_DB)


def _admin_conninfo(database_url: str) -> str:
    return _bounded(maintenance_url(database_url))


@dataclass(frozen=True)
class Probe:
    """What we could learn about the server without assuming our database exists."""

    server_up: bool
    database: str
    database_exists: bool
    reason: str | None = None


def probe(database_url: str) -> Probe:
    """Ask the server whether it is up and whether our database is there. Never raises.

    A missing database and an unreachable server produce the *same* libpq error class
    (`OperationalError` at connect time, with `sqlstate` left as None — the failure happens
    before a session exists to carry a SQLSTATE). Distinguishing them by parsing the message
    would be brittle, so we don't: we connect to the maintenance database instead and read
    `pg_database`. Server up + row absent means "create it"; connect failure means "the
    server is the problem".
    """
    name = database_name(database_url)
    try:
        with psycopg.connect(_admin_conninfo(database_url)) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            exists = cur.fetchone() is not None
    except psycopg.Error as exc:
        return Probe(server_up=False, database=name, database_exists=False, reason=str(exc))
    return Probe(server_up=True, database=name, database_exists=exists)


def _admin_connection(database_url: str) -> psycopg.Connection:
    """CREATE/DROP DATABASE cannot run inside a transaction block — hence autocommit."""
    return psycopg.connect(_admin_conninfo(database_url), autocommit=True)


def create_database(database_url: str) -> bool:
    """Create the database if absent. Returns True if it created one, False if already there."""
    name = database_name(database_url)
    if not name:
        raise ValueError("database URL carries no database name")
    with _admin_connection(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        if cur.fetchone() is not None:
            return False
        # The name comes from settings, not a request body, but quote it as an identifier
        # anyway — it cannot be a bound parameter, and Identifier is the only safe path.
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    return True


def drop_database(database_url: str) -> bool:
    """Drop the database if present. Returns True if it dropped one, False if already absent.

    Destructive — dev only. Postgres refuses to drop a database that has sessions attached,
    and our own API process is usually one of them, so evict every *other* backend first.
    """
    name = database_name(database_url)
    if not name:
        raise ValueError("database URL carries no database name")
    if name in {MAINTENANCE_DB, "template0", "template1"}:
        raise ValueError(f"refusing to drop the {name!r} database")
    with _admin_connection(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        if cur.fetchone() is None:
            return False
        cur.execute(
            """SELECT pg_terminate_backend(pid) FROM pg_stat_activity
               WHERE datname = %s AND pid <> pg_backend_pid()""",
            (name,),
        )
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
    return True


def create_tables(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()


def reset_tables(conn: psycopg.Connection) -> None:
    """Drop and recreate. Destructive — dev only."""
    with conn.cursor() as cur:
        cur.execute(DROP_SQL)
    conn.commit()
    create_tables(conn)


def tables_exist(conn: psycopg.Connection) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT count(*) FROM information_schema.tables
               WHERE table_schema = 'public' AND table_name IN ('photo_album', 'media')"""
        )
        return cur.fetchone()[0] == 2


def counts(conn: psycopg.Connection) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM photo_album")
        albums = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM media")
        media = cur.fetchone()[0]
    return {"photo_album": albums, "media": media}
