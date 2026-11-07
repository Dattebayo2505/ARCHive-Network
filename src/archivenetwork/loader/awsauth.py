"""App-scoped IAM Identity Center sign-in: the OAuth device flow `aws sso login` runs, in-process.

No AWS CLI and no `~/.aws` edits. The token cache lives at `<cache_dir>/<sha1(start_url)>.json`,
one file per start URL, so every env in the same organisation (dev and prod) shares one sign-in.
It holds the client registration and the SSO access/refresh tokens, plus the pending device code
while a sign-in is in flight. Role credentials (the short-lived AWS keys) are kept **in memory
only**, so the file holds no key that can sign an S3 or DynamoDB request. It is still a
credential: its access token (or the refresh token plus client secret) can mint role keys through
`GetRoleCredentials`, just like `~/.aws/sso/cache`. Treat it as one: it is written owner-only on
POSIX, and signing out deletes it.

`profile` envs skip all of this and use the named profile from the default AWS config; their
sign-in is `aws sso login --profile <name>`, run by the person, not by the app.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError, ProfileNotFound

from .envs import Env
from .storage import ENDPOINT_CONNECT_TIMEOUT, ENDPOINT_READ_TIMEOUT

LoginState = Literal["signed_out", "pending", "signed_in", "denied", "expired"]

CLIENT_NAME = "archivenetwork"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
REGISTRATION_MARGIN = 86_400  # renew the client registration a day before it lapses
PREVIEW_SECONDS = 900  # a presigned row preview's lifetime (routes_dev)
# A URL signed with these keys dies when they do, so refresh while a full preview still fits.
CREDENTIAL_MARGIN = PREVIEW_SECONDS
TOKEN_MARGIN = 60  # treat an access token as expired a minute early
# The same bounds as the env clients: an offline machine must not wait out 60 s x legacy retries.
AUTH_CONFIG = BotoConfig(
    connect_timeout=ENDPOINT_CONNECT_TIMEOUT,
    read_timeout=ENDPOINT_READ_TIMEOUT,
    retries={"mode": "standard", "total_max_attempts": 2},
)
# Refresh-token answers that mean the login is really gone; anything else is transient.
DEAD_REFRESH = frozenset({
    "InvalidGrantException", "ExpiredTokenException", "InvalidClientException",
    "UnauthorizedClientException",
})


@dataclass(frozen=True)
class DeviceLogin:
    verification_uri_complete: str
    user_code: str
    expires_in: int
    interval: int


class SignedOut(Exception):
    """No usable login for this env: absent, expired, or refused by Identity Center."""

    def __init__(self, env_name: str, reason: str = "") -> None:
        super().__init__(f"{env_name}: signed out" + (f" ({reason})" if reason else ""))
        self.env_name = env_name


class NotAssigned(Exception):
    """Signed in, but Identity Center won't hand out this env's role (`ForbiddenException`).

    The user isn't assigned that role in that account, or the overlay's `account_id` /
    `role_name` is mistyped. Signing in again can't fix it, so it must never read as signed out.
    """

    def __init__(self, env_name: str, role: str, account: str) -> None:
        # No closing period: the panel appends one ("AWS refused the request: <detail>.").
        super().__init__(
            f"not assigned role {role} in account {account} (check account_id and role_name "
            "in environments.local.toml, or ask an admin to assign you the role)"
        )
        self.env_name, self.role, self.account = env_name, role, account


def _code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


@dataclass(frozen=True)
class _RoleKeys:
    access_key_id: str
    secret_access_key: str
    session_token: str
    expires_at: float  # epoch seconds


class AuthManager:
    def __init__(
        self,
        cache_dir: Path,
        client_factory: Callable[..., Any] = boto3.client,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self._client = client_factory
        self._clock = clock
        # One lock per start URL (one cache file each), so a stalled call for one organisation
        # never holds up another's.
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        self._keys: dict[tuple[str, str, str], _RoleKeys] = {}

    def _lock(self, env: Env) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(env.sso.start_url, threading.RLock())

    # --- the cache file ---------------------------------------------------------------------

    def _path(self, env: Env) -> Path:
        digest = hashlib.sha1(env.sso.start_url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _load(self, env: Env) -> dict:
        try:
            return json.loads(self._path(env).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, env: Env, data: dict) -> None:
        path = self._path(env)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        if os.name == "posix":
            os.chmod(tmp, 0o600)  # it can mint role keys; Windows profiles are per-user already
        os.replace(tmp, path)  # atomic, so a crash never leaves half a token file

    def _oidc(self, env: Env):
        return self._client("sso-oidc", region_name=env.sso.region, config=AUTH_CONFIG)

    @staticmethod
    def _require_sso(env: Env) -> None:
        if env.kind != "aws":
            raise ValueError(f"{env.name} is a {env.kind} env; it needs no sign-in")
        if env.profile:
            raise ValueError(f"{env.name} uses a profile. Run: aws sso login --profile {env.profile}")
        if env.sso is None:
            raise ValueError(f"{env.name} has no [sso] table")

    # --- the device flow --------------------------------------------------------------------

    def _registration(self, env: Env, data: dict) -> dict:
        now = self._clock()
        if data.get("clientId") and data.get("registrationExpiresAt", 0) - REGISTRATION_MARGIN > now:
            return data
        reg = self._oidc(env).register_client(
            clientName=CLIENT_NAME, clientType="public", scopes=["sso:account:access"]
        )
        data.update(
            clientId=reg["clientId"],
            clientSecret=reg["clientSecret"],
            registrationExpiresAt=reg["clientSecretExpiresAt"],
        )
        return data

    def start_login(self, env: Env) -> DeviceLogin:
        self._require_sso(env)
        with self._lock(env):
            data = self._registration(env, self._load(env))
            resp = self._oidc(env).start_device_authorization(
                clientId=data["clientId"],
                clientSecret=data["clientSecret"],
                startUrl=env.sso.start_url,
            )
            login = DeviceLogin(
                verification_uri_complete=resp["verificationUriComplete"],
                user_code=resp["userCode"],
                expires_in=int(resp["expiresIn"]),
                interval=int(resp.get("interval") or 5),
            )
            data.update(deviceCode=resp["deviceCode"],
                        deviceCodeExpiresAt=self._clock() + login.expires_in)
            self._save(env, data)
            return login

    @staticmethod
    def _clear_device(data: dict) -> None:
        data.pop("deviceCode", None)
        data.pop("deviceCodeExpiresAt", None)

    def poll_login(self, env: Env) -> LoginState:
        """One `create_token` per call; the panel paces the polling at the server's interval."""
        if env.kind != "aws" or env.profile or env.sso is None:
            return self.state(env)
        with self._lock(env):
            data = self._load(env)
            if not data.get("deviceCode"):
                return self.state(env)
            # An abandoned sign-in (tab closed) must end as `expired`, never a forever-pending.
            if data.get("deviceCodeExpiresAt", 0) <= self._clock():
                self._clear_device(data)
                self._save(env, data)
                return "expired"
            try:
                tok = self._oidc(env).create_token(
                    clientId=data["clientId"],
                    clientSecret=data["clientSecret"],
                    grantType=DEVICE_GRANT,
                    deviceCode=data["deviceCode"],
                )
            except ClientError as exc:
                code = _code(exc)
                if code in ("AuthorizationPendingException", "SlowDownException"):
                    return "pending"
                self._clear_device(data)
                self._save(env, data)
                if code == "AccessDeniedException":
                    return "denied"
                if code == "ExpiredTokenException":
                    return "expired"
                raise
            self._clear_device(data)
            self._store_token(data, tok)
            self._save(env, data)
            self._forget_keys(env)
            return "signed_in"

    def _store_token(self, data: dict, tok: dict) -> None:
        data["accessToken"] = tok["accessToken"]
        data["expiresAt"] = self._clock() + int(tok.get("expiresIn", 0))
        if tok.get("refreshToken"):
            data["refreshToken"] = tok["refreshToken"]

    # --- state ------------------------------------------------------------------------------

    def _access_token(self, env: Env) -> str | None:
        """A live access token, refreshing once when it has expired. None when signed out.

        A refresh that fails for a transient reason (offline, throttled) raises and keeps the
        refresh token, so a moment without network never forces a full re-sign-in.
        """
        data = self._load(env)
        if data.get("accessToken") and data.get("expiresAt", 0) - TOKEN_MARGIN > self._clock():
            return data["accessToken"]
        if not (data.get("refreshToken") and data.get("clientId")):
            return None
        try:
            tok = self._oidc(env).create_token(
                clientId=data["clientId"],
                clientSecret=data["clientSecret"],
                grantType="refresh_token",
                refreshToken=data["refreshToken"],
            )
        except ClientError as exc:
            if _code(exc) not in DEAD_REFRESH:
                raise
            # Drop the dead refresh token, so the next state() answers without a network call.
            data.pop("refreshToken", None)
            self._save(env, data)
            return None
        self._store_token(data, tok)
        self._save(env, data)
        return data["accessToken"]

    def state(self, env: Env) -> LoginState:
        """No network for sso envs unless a token refresh is due.

        Raises `ProfileNotFound` for a profile env whose profile doesn't exist (it is not
        configured, not signed out), and a transient refresh failure (see `_access_token`).
        """
        if env.kind != "aws":
            return "signed_in"
        if env.profile:
            try:
                creds = boto3.Session(profile_name=env.profile).get_credentials()
            except ProfileNotFound:
                raise
            except BotoCoreError:
                creds = None
            return "signed_in" if creds is not None else "signed_out"
        if env.sso is None:
            return "signed_out"
        with self._lock(env):
            if self._access_token(env):
                return "signed_in"
            data = self._load(env)
            if data.get("deviceCode") and data.get("deviceCodeExpiresAt", 0) > self._clock():
                return "pending"
            return "signed_out"

    def logout(self, env: Env) -> None:
        if env.kind != "aws" or env.profile or env.sso is None:
            return
        with self._lock(env):
            self._path(env).unlink(missing_ok=True)
            self._forget_keys(env)

    # --- sessions ---------------------------------------------------------------------------

    def _forget_keys(self, env: Env) -> None:
        for key in [k for k in list(self._keys) if k[0] == env.sso.start_url]:
            self._keys.pop(key, None)

    def _drop_access_token(self, env: Env) -> None:
        """Identity Center revoked it: keep the refresh token, but stop calling this one live."""
        data = self._load(env)
        data.pop("accessToken", None)
        data.pop("expiresAt", None)
        self._save(env, data)
        self._forget_keys(env)

    def session(self, env: Env) -> boto3.Session:
        """The one session both of this env's clients come from: one identity per env."""
        if env.kind != "aws":
            raise ValueError(f"{env.name} is a {env.kind} env; it has no AWS session")
        if env.profile:
            return boto3.Session(profile_name=env.profile)
        if env.sso is None:
            raise SignedOut(env.name, "no [sso] table")
        sso = env.sso
        slot = (sso.start_url, sso.account_id, sso.role_name)
        with self._lock(env):
            keys = self._keys.get(slot)
            if keys is None or keys.expires_at - CREDENTIAL_MARGIN <= self._clock():
                token = self._access_token(env)
                if token is None:
                    raise SignedOut(env.name)
                try:
                    resp = self._client(
                        "sso", region_name=sso.region, config=AUTH_CONFIG
                    ).get_role_credentials(
                        roleName=sso.role_name, accountId=sso.account_id, accessToken=token
                    )
                except ClientError as exc:
                    code = _code(exc)
                    if code == "UnauthorizedException":
                        self._drop_access_token(env)
                        raise SignedOut(env.name, code) from exc
                    if code == "ForbiddenException":
                        raise NotAssigned(env.name, sso.role_name, sso.account_id) from exc
                    raise
                rc = resp["roleCredentials"]
                keys = _RoleKeys(rc["accessKeyId"], rc["secretAccessKey"], rc["sessionToken"],
                                 rc["expiration"] / 1000)
                self._keys[slot] = keys
        return boto3.Session(
            aws_access_key_id=keys.access_key_id,
            aws_secret_access_key=keys.secret_access_key,
            aws_session_token=keys.session_token,
            region_name=env.region,
        )
