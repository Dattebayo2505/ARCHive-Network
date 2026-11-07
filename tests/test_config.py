from archivenetwork.config import Settings, settings


def test_defaults():
    assert settings.max_per_album == 10
    assert settings.thumb_size == 512


def test_env_override(monkeypatch):
    monkeypatch.setenv("ARCHIVENETWORK_MAX_PER_ALBUM", "5")
    assert Settings().max_per_album == 5


# --- the environment registry + stale .env report ---


def test_settings_no_longer_declare_aws_fields():
    from archivenetwork.config import STALE_KEYS

    s = Settings(_env_file=None)
    for key in STALE_KEYS:
        name = key.removeprefix("ARCHIVENETWORK_").lower()
        assert not hasattr(s, name), name
        assert name not in Settings.model_fields, name


def test_settings_point_at_the_environment_files():
    from archivenetwork.config import PROJECT_ROOT

    s = Settings(_env_file=None)
    assert s.environments_file == PROJECT_ROOT / "environments.toml"
    assert s.environments_local_file == PROJECT_ROOT / "environments.local.toml"


def test_stale_settings_reads_env_file_and_environ(tmp_path):
    from archivenetwork.config import stale_settings

    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nARCHIVENETWORK_S3_BUCKET=x\nARCHIVENETWORK_PORT=1\n")
    environ = {"ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX": "y", "PATH": "/bin"}
    assert stale_settings(env_file, environ) == [
        "ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX",
        "ARCHIVENETWORK_S3_BUCKET",
    ]


def test_stale_settings_never_returns_values(tmp_path):
    from archivenetwork.config import stale_settings

    env_file = tmp_path / ".env"
    env_file.write_text("ARCHIVENETWORK_S3_SECRET_ACCESS_KEY=hunter2-secret\n")
    result = stale_settings(env_file, {"ARCHIVENETWORK_S3_ACCESS_KEY_ID": "AKIAEXAMPLEVALUE"})
    assert "hunter2-secret" not in repr(result)
    assert "AKIAEXAMPLEVALUE" not in repr(result)
    assert result == ["ARCHIVENETWORK_S3_ACCESS_KEY_ID", "ARCHIVENETWORK_S3_SECRET_ACCESS_KEY"]


def test_stale_settings_without_an_env_file(tmp_path):
    from archivenetwork.config import stale_settings

    assert stale_settings(tmp_path / "missing.env", {}) == []


def test_stale_keys_cover_every_retired_setting():
    from archivenetwork.config import STALE_KEYS

    assert "ARCHIVENETWORK_DYNAMODB_TABLE" in STALE_KEYS
    assert "ARCHIVENETWORK_MEDIA_BASE_URL" in STALE_KEYS
    assert len(STALE_KEYS) == 11


def test_app_state_has_registry():
    from archivenetwork.app import create_app

    app = create_app()
    assert app.state.envs.default == "local"
    assert app.state.envs.floci().kind == "floci"


def test_app_warns_about_stale_settings(tmp_path, monkeypatch, caplog):
    import logging

    from archivenetwork.app import create_app

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("ARCHIVENETWORK_FLOCI_BUCKET=old-secret-bucket\n")
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        create_app()
    warned = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("ARCHIVENETWORK_FLOCI_BUCKET" in m for m in warned)
    assert not any("old-secret-bucket" in m for m in warned)
