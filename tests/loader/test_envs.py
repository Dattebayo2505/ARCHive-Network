"""The environment registry: the committed `environments.toml` plus a gitignored overlay."""

from __future__ import annotations

from pathlib import Path

import pytest

from archivenetwork.loader.envs import EnvConfigError, UnknownEnv, load_registry

REPO = Path(__file__).resolve().parents[2]
COMMITTED = REPO / "environments.toml"

FLOCI = """
[env.local]
kind = "floci"
label = "Local"
endpoint_url = "http://127.0.0.1:4566"
region = "ap-southeast-1"
s3_bucket = "local-bucket"
table_prefix = "an-local"
"""

AWS_ENV = """
[env.{name}]
kind = "aws"
label = "{name}"
region = "ap-southeast-1"
s3_bucket = "{bucket}"
table_prefix = "{prefix}"
[env.{name}.sso]
start_url = "https://example.awsapps.com/start"
region = "ap-southeast-1"
account_id = "{account}"
role_name = "Curators"
"""


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _committed(tmp_path: Path, extra: str = "") -> Path:
    return _write(tmp_path / "environments.toml", 'default = "local"\n' + FLOCI + extra)


def _overlay(tmp_path: Path, text: str) -> Path:
    return _write(tmp_path / "environments.local.toml", text)


def test_committed_file_defines_local_dev_prod():
    reg = load_registry(COMMITTED)
    assert set(reg.envs) == {"local", "dev", "prod"}
    assert reg.default == "local"
    assert reg.envs["local"].kind == "floci"
    assert reg.envs["prod"].confirm is True
    assert reg.envs["dev"].configured is False
    assert reg.errors == []


def test_committed_file_holds_no_account_ids():
    reg = load_registry(COMMITTED)
    aws = [e for e in reg.envs.values() if e.kind == "aws"]
    assert aws
    for env in aws:
        assert env.sso is not None
        assert env.sso.account_id == ""
        assert env.sso.start_url == ""


def test_overlay_fills_sso_key_by_key(tmp_path):
    overlay = _overlay(
        tmp_path,
        '[env.dev.sso]\nstart_url = "https://d-x.awsapps.com/start"\naccount_id = "111122223333"\n',
    )
    reg = load_registry(COMMITTED, overlay)
    dev = reg.envs["dev"]
    assert dev.sso.role_name == "Curators"  # kept from the committed file
    assert dev.sso.account_id == "111122223333"
    assert dev.configured is True
    assert reg.envs["prod"].configured is False
    assert reg.errors == []


def test_overlay_adds_an_env(tmp_path):
    overlay = _overlay(
        tmp_path,
        AWS_ENV.format(name="personal", bucket="me-alpha", prefix="an-personal",
                       account="444455556666"),
    )
    reg = load_registry(COMMITTED, overlay)
    assert reg.envs["personal"].kind == "aws"
    assert reg.envs["personal"].configured is True


def test_example_overlay_is_a_valid_overlay():
    reg = load_registry(COMMITTED, REPO / "environments.local.toml.example")
    assert reg.errors == []
    assert {"dev", "prod", "personal"} <= set(reg.envs)
    assert all(reg.envs[n].configured for n in ("dev", "prod", "personal"))


def test_overlay_default_is_ignored(tmp_path):
    overlay = _overlay(tmp_path, 'default = "dev"\n')
    assert load_registry(COMMITTED, overlay).default == "local"


def test_missing_overlay_is_fine(tmp_path):
    reg = load_registry(COMMITTED, tmp_path / "environments.local.toml")
    assert reg.errors == []
    assert set(reg.envs) == {"local", "dev", "prod"}


def test_broken_overlay_is_ignored_and_reported(tmp_path):
    overlay = _overlay(tmp_path, "[env.dev\n")
    reg = load_registry(COMMITTED, overlay)
    assert reg.envs == load_registry(COMMITTED).envs
    assert len(reg.errors) == 1
    assert "environments.local.toml" in reg.errors[0]


def test_invalid_overlay_env_is_reported(tmp_path):
    text = AWS_ENV.format(name="personal", bucket="x", prefix="an-personal", account="1")
    text = text.replace('s3_bucket = "x"\n', "")
    reg = load_registry(COMMITTED, _overlay(tmp_path, text))
    assert "personal" not in reg.envs
    assert len(reg.errors) == 1
    assert "s3_bucket" in reg.errors[0]
    assert "environments.local.toml" in reg.errors[0]


def test_broken_committed_file_raises(tmp_path):
    with pytest.raises(EnvConfigError):
        load_registry(_write(tmp_path / "environments.toml", "[env.local\n"))


def test_missing_committed_file_raises(tmp_path):
    with pytest.raises(EnvConfigError):
        load_registry(tmp_path / "nope.toml")


def test_default_must_be_floci(tmp_path):
    text = 'default = "dev"\n' + FLOCI + AWS_ENV.format(
        name="dev", bucket="b", prefix="an-dev", account=""
    )
    with pytest.raises(EnvConfigError, match="default"):
        load_registry(_write(tmp_path / "environments.toml", text))


def test_floci_needs_an_endpoint(tmp_path):
    text = 'default = "local"\n' + FLOCI.replace('endpoint_url = "http://127.0.0.1:4566"\n', "")
    with pytest.raises(EnvConfigError, match="endpoint_url"):
        load_registry(_write(tmp_path / "environments.toml", text))


def test_aws_needs_sso_or_profile(tmp_path):
    bare = '\n[env.dev]\nkind = "aws"\nlabel = "d"\nregion = "r"\ns3_bucket = "b"\ntable_prefix = "p"\n'
    with pytest.raises(EnvConfigError, match="sso"):
        load_registry(_committed(tmp_path, bare))
    ok = load_registry(_committed(tmp_path, bare + 'profile = "mine"\n'))
    assert ok.envs["dev"].configured is True
    assert ok.envs["dev"].profile == "mine"


def test_sso_needs_all_four_keys(tmp_path):
    text = AWS_ENV.format(name="dev", bucket="b", prefix="an-dev", account="").replace(
        'role_name = "Curators"\n', ""
    )
    with pytest.raises(EnvConfigError, match="role_name"):
        load_registry(_committed(tmp_path, text))


def test_env_name_pattern(tmp_path):
    bad = AWS_ENV.format(name="Prod", bucket="b", prefix="an-prod", account="")
    with pytest.raises(EnvConfigError, match="Prod"):
        load_registry(_committed(tmp_path, bad))
    good = AWS_ENV.format(name="my-test", bucket="b", prefix="an-my-test", account="")
    assert "my-test" in load_registry(_committed(tmp_path, good)).envs


def test_same_account_cannot_share_bucket_or_prefix(tmp_path):
    same_prefix = AWS_ENV.format(
        name="dev", bucket="b1", prefix="an", account="111122223333"
    ) + AWS_ENV.format(name="prod", bucket="b2", prefix="an", account="111122223333")
    with pytest.raises(EnvConfigError, match="table_prefix"):
        load_registry(_committed(tmp_path, same_prefix))
    same_bucket = AWS_ENV.format(
        name="dev", bucket="b", prefix="an-dev", account="111122223333"
    ) + AWS_ENV.format(name="prod", bucket="b", prefix="an-prod", account="111122223333")
    with pytest.raises(EnvConfigError, match="s3_bucket"):
        load_registry(_committed(tmp_path, same_bucket))
    # Different accounts may reuse a prefix: the tables can't collide.
    other = AWS_ENV.format(
        name="dev", bucket="b1", prefix="an", account="111122223333"
    ) + AWS_ENV.format(name="prod", bucket="b2", prefix="an", account="999988887777")
    assert set(load_registry(_committed(tmp_path, other)).envs) == {"local", "dev", "prod"}


def test_overlay_collision_with_committed_env_is_reported(tmp_path):
    """Same floci endpoint, same prefix: the overlay env would share the local tables."""
    overlay = _overlay(tmp_path, FLOCI.replace("env.local", "env.scratch").replace("local-bucket", "other"))
    reg = load_registry(_committed(tmp_path), overlay)
    assert "scratch" not in reg.envs
    assert "table_prefix" in reg.errors[0]


def test_public_dict_hides_sso(tmp_path):
    overlay = _overlay(
        tmp_path,
        '[env.dev.sso]\nstart_url = "https://d-x.awsapps.com/start"\naccount_id = "111122223333"\n',
    )
    reg = load_registry(COMMITTED, overlay)
    env = reg.envs["dev"]
    pub = env.public()
    assert "sso" not in pub
    assert "account_id" not in str(pub)
    assert "111122223333" not in str(pub)
    assert "awsapps" not in str(pub)
    assert "endpoint_url" not in pub
    assert set(pub) == {"name", "label", "kind", "region", "s3_bucket", "table_prefix",
                        "confirm", "configured"}


def test_public_dict_carries_the_floci_endpoint():
    pub = load_registry(COMMITTED).envs["local"].public()
    assert pub["endpoint_url"] == "http://127.0.0.1:4566"


def test_get_unknown_raises():
    reg = load_registry(COMMITTED)
    assert reg.get("local").name == "local"
    assert reg.floci().name == "local"
    with pytest.raises(UnknownEnv):
        reg.get("nope")


# --- review round 1 ----------------------------------------------------------------------


def test_utf16_overlay_is_ignored_and_reported(tmp_path):
    # I2: Windows PowerShell 5's `>` writes UTF-16; startup must survive it.
    overlay = tmp_path / "environments.local.toml"
    overlay.write_bytes('[env.dev]\nlabel = "Dev"\n'.encode("utf-16"))
    reg = load_registry(COMMITTED, overlay)
    assert set(reg.envs) == {"local", "dev", "prod"}
    assert len(reg.errors) == 1
    assert "environments.local.toml" in reg.errors[0]
    assert "UTF-8" in reg.errors[0]


def test_cp1252_overlay_is_ignored_and_reported(tmp_path):
    overlay = tmp_path / "environments.local.toml"
    overlay.write_bytes('[env.dev]\nlabel = "Café"\n'.encode("cp1252"))
    reg = load_registry(COMMITTED, overlay)
    assert reg.envs["dev"].label == "Dev (AWS)"
    assert "UTF-8" in reg.errors[0]


def test_utf8_bom_overlay_parses(tmp_path):
    overlay = tmp_path / "environments.local.toml"
    overlay.write_bytes('[env.dev]\nlabel = "Dev ✓"\n'.encode("utf-8-sig"))
    reg = load_registry(COMMITTED, overlay)
    assert reg.errors == []
    assert reg.envs["dev"].label == "Dev ✓"


def test_non_utf8_committed_file_raises(tmp_path):
    path = tmp_path / "environments.toml"
    path.write_bytes(('default = "local"\n' + FLOCI).encode("utf-16"))
    with pytest.raises(EnvConfigError, match="UTF-8"):
        load_registry(path)


def test_overlay_cannot_turn_off_a_committed_confirm(tmp_path):
    # I4: the typed confirm is prod's only write guard.
    overlay = _overlay(tmp_path, "[env.prod]\nconfirm = false\n")
    reg = load_registry(COMMITTED, overlay)
    assert reg.envs["prod"].confirm is True
    assert len(reg.errors) == 1
    assert "env.prod.confirm" in reg.errors[0]
    assert "environments.local.toml was ignored" in reg.errors[0]


def test_overlay_may_turn_a_confirm_on(tmp_path):
    overlay = _overlay(tmp_path, "[env.dev]\nconfirm = true\n")
    reg = load_registry(COMMITTED, overlay)
    assert reg.errors == []
    assert reg.envs["dev"].confirm is True


@pytest.mark.parametrize("other", [
    "http://localhost:4566", "http://127.0.0.1:4566/", "HTTP://LOCALHOST:4566/",
])
def test_floci_collision_normalizes_the_endpoint(tmp_path, other):
    # M13: the same emulator spelled two ways still shares one bucket namespace.
    extra = FLOCI.replace("[env.local]", "[env.other]").replace(
        "http://127.0.0.1:4566", other).replace("an-local", "an-other")
    with pytest.raises(EnvConfigError, match="s3_bucket"):
        load_registry(_committed(tmp_path, extra))


def test_floci_envs_on_different_ports_may_share_a_bucket(tmp_path):
    extra = FLOCI.replace("[env.local]", "[env.other]").replace(
        "127.0.0.1:4566", "127.0.0.1:4567").replace("an-local", "an-other")
    assert set(load_registry(_committed(tmp_path, extra)).envs) == {"local", "other"}


# --- review round 2 ----------------------------------------------------------------------

PROD_TWIN = """
[env.mine]
kind = "aws"
label = "Mine"
region = "ap-southeast-1"
s3_bucket = "{bucket}"
table_prefix = "{prefix}"
profile = "my-profile"
{confirm}
"""


@pytest.mark.parametrize("bucket, prefix, key", [
    ("archers-network-media-prod", "an-mine", "s3_bucket"),
    ("mine-bucket", "archers-network-prod", "table_prefix"),
])
def test_an_overlay_env_aimed_at_prods_resources_needs_the_confirm(tmp_path, bucket, prefix, key):
    # A profile env has no account to collide on, so it could reach prod with no typed confirm.
    overlay = _overlay(tmp_path, PROD_TWIN.format(bucket=bucket, prefix=prefix, confirm=""))
    reg = load_registry(COMMITTED, overlay)
    assert "mine" not in reg.envs
    assert len(reg.errors) == 1
    assert f"env.mine.{key}" in reg.errors[0] and "env.prod" in reg.errors[0]
    assert "environments.local.toml was ignored" in reg.errors[0]


def test_an_overlay_env_aimed_at_prods_resources_with_the_confirm_is_fine(tmp_path):
    overlay = _overlay(tmp_path, PROD_TWIN.format(
        bucket="archers-network-media-prod", prefix="archers-network-prod", confirm="confirm = true"))
    reg = load_registry(COMMITTED, overlay)
    assert reg.errors == []
    assert reg.envs["mine"].confirm is True
