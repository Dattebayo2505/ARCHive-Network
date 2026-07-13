from pathlib import Path

from archivenetwork.config import Settings, settings


def test_defaults():
    assert settings.max_per_album == 10
    assert settings.thumb_size == 512


def test_env_override(monkeypatch):
    monkeypatch.setenv("ARCHIVENETWORK_MAX_PER_ALBUM", "5")
    assert Settings().max_per_album == 5


def test_devmode_settings_default_off(monkeypatch):
    monkeypatch.delenv("ARCHIVENETWORK_DATABASE_URL", raising=False)
    # `.env` at the repo root would otherwise leak a real URL into this assertion.
    s = Settings(_env_file=None)
    assert s.database_url is None  # dev-mode is opt-in
    # The store root must not be named "media" — keys already start with "media/", so a
    # "media" root would double-nest every object (workspace/media/media/2026/...).
    assert s.media_root == Path("workspace/store")
    assert s.media_base_url == "/store"


def test_database_url_from_env(monkeypatch):
    monkeypatch.setenv("ARCHIVENETWORK_DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    assert Settings().database_url == "postgresql://u:p@localhost:5432/db"
