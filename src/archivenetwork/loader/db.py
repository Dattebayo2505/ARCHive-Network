"""PostgreSQL connection and schema.

Only the two tables this ETL actually populates (PLAN §4). Taxonomy, contributors and users are
CMS-overlay concerns with no source in the export — `media` deliberately has **no
`category_id`**; the CMS adds that FK later. Pretending otherwise would defeat the point of
validating the schema against real data.
"""

from __future__ import annotations

import psycopg

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS photo_album (
    fb_album_id  text PRIMARY KEY,
    title        text NOT NULL,
    description  text,
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
    caption             text,
    description         text,
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
"""

DROP_SQL = "DROP TABLE IF EXISTS media; DROP TABLE IF EXISTS photo_album;"


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url)


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
