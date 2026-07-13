import psycopg
import pytest

from archivenetwork.loader import db


def test_create_tables_is_idempotent(pg_conn):
    assert db.tables_exist(pg_conn) is True
    db.create_tables(pg_conn)  # second run must not raise
    assert db.tables_exist(pg_conn) is True


def test_counts_start_empty(pg_conn):
    assert db.counts(pg_conn) == {"photo_album": 0, "media": 0}


def test_media_fbid_is_unique(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO media (fbid, media_type, storage_path) VALUES (%s,%s,%s)",
            ("dup", "photo", "media/2026/01/01/dup.jpg"),
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO media (fbid, media_type, storage_path) VALUES (%s,%s,%s)",
                ("dup", "photo", "media/2026/01/01/dup.jpg"),
            )
    pg_conn.rollback()


def test_media_type_is_constrained(pg_conn):
    with pg_conn.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO media (fbid, media_type, storage_path) VALUES (%s,%s,%s)",
            ("x", "audio", "media/2026/01/01/x.jpg"),
        )
    pg_conn.rollback()
