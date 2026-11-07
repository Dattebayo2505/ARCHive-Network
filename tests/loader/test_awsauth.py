"""App-scoped IAM Identity Center sign-in, against stub `sso-oidc` / `sso` clients.

moto does not emulate Identity Center, so the clients are fakes that record their calls.
"""

from __future__ import annotations

import json

import pytest
from botocore.exceptions import ClientError

from archivenetwork.loader.awsauth import AuthManager, DeviceLogin, SignedOut
from archivenetwork.loader.envs import Env, Sso

START = "https://d-test.awsapps.com/start"
NOW = 1_800_000_000.0


def _env(name="dev", start_url=START, account="111122223333", **over) -> Env:
    base = dict(
        name=name, kind="aws", label=name, region="ap-southeast-1",
        s3_bucket=f"{name}-bucket", table_prefix=f"an-{name}",
        sso=Sso(start_url, "ap-southeast-1", account, "Curators"),
    )
    return Env(**{**base, **over})


def _err(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "Op")


class Clock:
    def __init__(self, t: float = NOW):
        self.t = t

    def __call__(self) -> float:
        return self.t


class FakeOidc:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.token_results: list = []  # popped per create_token call: dict or exception
        self.refresh_result = None

    def register_client(self, **kw):
        self.calls.append(("register_client", kw))
        return {"clientId": "cid", "clientSecret": "csecret",
                "clientSecretExpiresAt": int(NOW) + 90 * 86400}

    def start_device_authorization(self, **kw):
        self.calls.append(("start_device_authorization", kw))
        return {"deviceCode": "dcode", "userCode": "ABCD-EFGH",
                "verificationUri": "https://device.sso/", "expiresIn": 600, "interval": 5,
                "verificationUriComplete": "https://device.sso/?user_code=ABCD-EFGH"}

    def create_token(self, **kw):
        self.calls.append(("create_token", kw))
        if kw["grantType"] == "refresh_token":
            r = self.refresh_result
        else:
            r = self.token_results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def count(self, name: str) -> int:
        return sum(1 for n, _ in self.calls if n == name)


class FakeSso:
    def __init__(self, clock: Clock):
        self.clock = clock
        self.calls: list[dict] = []
        self.ttl = 3600

    def get_role_credentials(self, **kw):
        self.calls.append(kw)
        return {"roleCredentials": {
            "accessKeyId": "ASIAFAKE", "secretAccessKey": "fake-secret-key",
            "sessionToken": "fake-session", "expiration": int((self.clock() + self.ttl) * 1000),
        }}


TOKENS = {"accessToken": "atok", "refreshToken": "rtok", "expiresIn": 3600}


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def fakes(clock):
    return {"sso-oidc": FakeOidc(), "sso": FakeSso(clock)}


@pytest.fixture
def auth(tmp_path, fakes, clock):
    return AuthManager(tmp_path / "sso", client_factory=lambda svc, **kw: fakes[svc], clock=clock)


def _sign_in(auth, fakes, env):
    auth.start_login(env)
    fakes["sso-oidc"].token_results.append(dict(TOKENS))
    assert auth.poll_login(env) == "signed_in"


def test_start_login_registers_once_and_returns_device_code(auth, fakes):
    env = _env()
    first = auth.start_login(env)
    second = auth.start_login(env)
    assert fakes["sso-oidc"].count("register_client") == 1
    assert first == second == DeviceLogin(
        verification_uri_complete="https://device.sso/?user_code=ABCD-EFGH",
        user_code="ABCD-EFGH", expires_in=600, interval=5,
    )
    start = [kw for n, kw in fakes["sso-oidc"].calls if n == "start_device_authorization"][0]
    assert start["startUrl"] == START


def test_registration_is_renewed_a_day_before_it_expires(auth, fakes, clock):
    env = _env()
    auth.start_login(env)
    clock.t = NOW + 89 * 86400 + 1  # inside the last day of the 90-day registration
    auth.start_login(env)
    assert fakes["sso-oidc"].count("register_client") == 2


def test_poll_pending_then_signed_in(auth, fakes, tmp_path):
    env = _env()
    auth.start_login(env)
    assert auth.state(env) == "pending"
    fakes["sso-oidc"].token_results += [_err("AuthorizationPendingException"), dict(TOKENS)]
    assert [auth.poll_login(env), auth.poll_login(env)] == ["pending", "signed_in"]
    assert list((tmp_path / "sso").glob("*.json"))
    assert auth.state(env) == "signed_in"


def test_slow_down_is_still_pending(auth, fakes):
    env = _env()
    auth.start_login(env)
    fakes["sso-oidc"].token_results.append(_err("SlowDownException"))
    assert auth.poll_login(env) == "pending"


def test_poll_expired_device_code(auth, fakes):
    env = _env()
    auth.start_login(env)
    fakes["sso-oidc"].token_results.append(_err("ExpiredTokenException"))
    assert auth.poll_login(env) == "expired"
    assert auth.state(env) == "signed_out"


def test_abandoned_device_code_expires_without_a_call(auth, fakes, clock):
    env = _env()
    auth.start_login(env)
    clock.t = NOW + 601
    assert auth.poll_login(env) == "expired"
    assert fakes["sso-oidc"].count("create_token") == 0
    assert auth.state(env) == "signed_out"


def test_poll_denied(auth, fakes):
    env = _env()
    auth.start_login(env)
    fakes["sso-oidc"].token_results.append(_err("AccessDeniedException"))
    assert auth.poll_login(env) == "denied"
    assert auth.state(env) == "signed_out"


def test_dev_and_prod_share_one_login(auth, fakes):
    dev, prod = _env("dev"), _env("prod")
    _sign_in(auth, fakes, dev)
    assert auth.state(prod) == "signed_in"


def test_session_caches_role_credentials_until_near_expiry(auth, fakes, clock):
    env = _env()
    _sign_in(auth, fakes, env)
    s1 = auth.session(env)
    auth.session(env)
    assert len(fakes["sso"].calls) == 1
    call = fakes["sso"].calls[0]
    assert call == {"roleName": "Curators", "accountId": "111122223333", "accessToken": "atok"}
    assert s1.get_credentials().access_key == "ASIAFAKE"
    assert s1.region_name == "ap-southeast-1"
    clock.t = NOW + 3600 - 299  # inside the 5-minute margin
    fakes["sso"].ttl = 7200
    fakes["sso-oidc"].refresh_result = dict(TOKENS)
    auth.session(env)
    assert len(fakes["sso"].calls) == 2


def test_expired_access_token_refreshes_once(auth, fakes, clock):
    env = _env()
    _sign_in(auth, fakes, env)
    clock.t = NOW + 4000  # past expiresAt
    fakes["sso-oidc"].refresh_result = {"accessToken": "atok2", "expiresIn": 3600}
    auth.session(env)
    assert fakes["sso"].calls[-1]["accessToken"] == "atok2"
    assert fakes["sso-oidc"].count("create_token") == 2  # device code + one refresh

    clock.t = NOW + 9000
    fakes["sso-oidc"].refresh_result = _err("InvalidGrantException")
    with pytest.raises(SignedOut) as info:
        auth.session(env)
    assert info.value.env_name == "dev"
    assert fakes["sso-oidc"].count("create_token") == 3
    assert auth.state(env) == "signed_out"
    assert fakes["sso-oidc"].count("create_token") == 3  # a failed refresh is not retried


def test_session_without_login_is_signed_out(auth):
    with pytest.raises(SignedOut):
        auth.session(_env())


def test_unauthorized_role_credentials_are_signed_out(auth, fakes):
    env = _env()
    _sign_in(auth, fakes, env)

    def refuse(**kw):
        raise _err("UnauthorizedException")

    fakes["sso"].get_role_credentials = refuse
    with pytest.raises(SignedOut):
        auth.session(env)


def test_logout_removes_cache_file(auth, fakes, tmp_path):
    env = _env()
    _sign_in(auth, fakes, env)
    auth.session(env)
    auth.logout(env)
    assert not list((tmp_path / "sso").glob("*.json"))
    assert auth.state(env) == "signed_out"
    with pytest.raises(SignedOut):
        auth.session(env)


def test_cache_file_never_contains_role_credentials(auth, fakes, tmp_path):
    env = _env()
    _sign_in(auth, fakes, env)
    auth.session(env)
    (cache,) = (tmp_path / "sso").glob("*.json")
    text = cache.read_text(encoding="utf-8")
    assert "secretAccessKey" not in text
    assert "fake-secret-key" not in text
    assert json.loads(text)["accessToken"] == "atok"


def test_profile_env_uses_the_named_profile(auth, monkeypatch):
    import boto3

    env = _env(sso=None, profile="mine")
    made = []

    class FakeSession:
        def __init__(self, profile_name):
            made.append(profile_name)

        def get_credentials(self):
            return None

    monkeypatch.setattr(boto3, "Session", FakeSession)
    assert auth.state(env) == "signed_out"
    assert isinstance(auth.session(env), FakeSession)
    assert made == ["mine", "mine"]
    with pytest.raises(ValueError, match="aws sso login --profile mine"):
        auth.start_login(env)


def test_floci_env_is_always_signed_in(auth):
    env = Env("local", "floci", "L", "ap-southeast-1", "b", "p", endpoint_url="http://x:1")
    assert auth.state(env) == "signed_in"
    with pytest.raises(ValueError):
        auth.start_login(env)
