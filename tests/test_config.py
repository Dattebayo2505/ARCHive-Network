from streamlinify.config import Settings, settings


def test_defaults():
    assert settings.max_per_album == 10
    assert settings.thumb_size == 512


def test_env_override(monkeypatch):
    monkeypatch.setenv("STREAMLINIFY_MAX_PER_ALBUM", "5")
    assert Settings().max_per_album == 5
