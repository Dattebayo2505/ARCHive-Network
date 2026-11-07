"""Named environments: each pairs one S3 bucket with one DynamoDB table prefix and one identity.

Environments are data. `environments.toml` (committed) defines the official ones with empty SSO
identifiers, because the repo is assumed public; a gitignored `environments.local.toml` is merged
over it key by key to fill those in or add personal envs. The code knows two *kinds* (`floci`,
`aws`) and nothing about specific names.

A broken committed file is a startup failure (`EnvConfigError`). A broken overlay is not: it is
dropped whole and reported in `Registry.errors`, so a typo in a personal file never stops the app
from running on the committed envs.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

EnvKind = Literal["floci", "aws"]
KINDS: tuple[str, ...] = ("floci", "aws")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
REQUIRED = ("kind", "label", "region", "s3_bucket", "table_prefix")
SSO_KEYS = ("start_url", "region", "account_id", "role_name")


class EnvConfigError(Exception):
    """An environments file is unreadable or invalid; the message names the file and key."""


class UnknownEnv(KeyError):
    """No environment has that name."""


@dataclass(frozen=True)
class Sso:
    start_url: str
    region: str
    account_id: str
    role_name: str


@dataclass(frozen=True)
class Env:
    name: str
    kind: EnvKind
    label: str
    region: str
    s3_bucket: str
    table_prefix: str
    confirm: bool = False
    endpoint_url: str | None = None  # floci only
    sso: Sso | None = None  # aws: sso or profile
    profile: str | None = None

    @property
    def configured(self) -> bool:
        if self.kind == "floci":
            return True
        if self.profile:
            return True
        return bool(self.sso and self.sso.start_url and self.sso.account_id)

    def public(self) -> dict:
        """What the browser may see: never SSO identifiers or a profile name."""
        out: dict[str, Any] = {
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "region": self.region,
            "s3_bucket": self.s3_bucket,
            "table_prefix": self.table_prefix,
            "confirm": self.confirm,
            "configured": self.configured,
        }
        if self.kind == "floci":
            out["endpoint_url"] = self.endpoint_url
        return out


@dataclass(frozen=True)
class Registry:
    default: str
    envs: dict[str, Env]
    errors: list[str] = field(default_factory=list)

    def get(self, name: str) -> Env:
        try:
            return self.envs[name]
        except KeyError:
            raise UnknownEnv(name) from None

    def floci(self) -> Env:
        """The default env, which validation guarantees is a floci one."""
        return self.envs[self.default]


# --- parsing ---------------------------------------------------------------------------------


def _read(path: Path) -> dict:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise EnvConfigError(f"{path.name}: cannot read ({exc})") from exc
    # utf-8-sig accepts a BOM (Notepad); UTF-16 (PowerShell 5's `>`) and ANSI files are refused
    # by name rather than raising out of create_app().
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EnvConfigError(f"{path.name}: not UTF-8 text ({exc}); save it as UTF-8") from exc
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise EnvConfigError(f"{path.name}: invalid TOML ({exc})") from exc


def _env_tables(raw: dict, label: str) -> dict[str, dict]:
    envs = raw.get("env", {})
    if not isinstance(envs, dict):
        raise EnvConfigError(f"{label}: `env` must be a table of environments")
    for name, table in envs.items():
        if not isinstance(table, dict):
            raise EnvConfigError(f"{label}: env.{name} must be a table")
    return envs


def _merge(base: dict[str, dict], over: dict[str, dict]) -> dict[str, dict]:
    """Key by key within each env, and within its nested `sso` table."""
    out = {name: {**table} for name, table in base.items()}
    for name, table in over.items():
        merged = out.setdefault(name, {})
        for key, value in table.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
    return out


def _string(table: dict, key: str, where: str) -> str:
    value = table.get(key)
    if not isinstance(value, str):
        raise EnvConfigError(f"{where}.{key} must be a string")
    return value


def _build(name: str, table: dict, label: str) -> Env:
    where = f"{label}: env.{name}"
    if not NAME_RE.match(name):
        raise EnvConfigError(f"{where}: name {name!r} must match {NAME_RE.pattern}")
    for key in REQUIRED:
        if key not in table:
            raise EnvConfigError(f"{where}: missing required key `{key}`")
    kind = _string(table, "kind", where)
    if kind not in KINDS:
        raise EnvConfigError(f"{where}.kind must be one of {KINDS}, not {kind!r}")
    confirm = table.get("confirm", False)
    if not isinstance(confirm, bool):
        raise EnvConfigError(f"{where}.confirm must be true or false")
    common = {
        key: _string(table, key, where) for key in ("label", "region", "s3_bucket", "table_prefix")
    }
    if kind == "floci":
        if "endpoint_url" not in table:
            raise EnvConfigError(f"{where}: floci envs need `endpoint_url`")
        return Env(name, "floci", confirm=confirm,
                   endpoint_url=_string(table, "endpoint_url", where), **common)

    sso_raw = table.get("sso")
    profile = table.get("profile")
    if profile is not None and not isinstance(profile, str):
        raise EnvConfigError(f"{where}.profile must be a string")
    sso = None
    if sso_raw is not None:
        if not isinstance(sso_raw, dict):
            raise EnvConfigError(f"{where}.sso must be a table")
        for key in SSO_KEYS:
            if key not in sso_raw:
                raise EnvConfigError(f"{where}.sso: missing key `{key}` (it may be empty)")
        sso = Sso(**{key: _string(sso_raw, key, f"{where}.sso") for key in SSO_KEYS})
    if sso is None and not profile:
        raise EnvConfigError(f"{where}: aws envs need an [env.{name}.sso] table or `profile`")
    return Env(name, "aws", confirm=confirm, sso=sso, profile=profile or None, **common)


def _endpoint_scope(url: str | None) -> tuple:
    """One emulator however it is spelled: `localhost` is 127.0.0.1, case and a trailing `/` drop."""
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    if host in ("localhost", "::1"):
        host = "127.0.0.1"
    try:
        port = parts.port
    except ValueError:
        port = None
    return (parts.scheme.lower(), host, port, parts.path.rstrip("/"))


def _check_collisions(envs: dict[str, Env], label: str) -> None:
    """No two envs that reach the same tables/bucket: the guard behind same-account dev/prod."""
    seen: dict[tuple, str] = {}
    for env in envs.values():
        if env.kind == "floci":
            scope: tuple = ("floci", *_endpoint_scope(env.endpoint_url))
        elif env.sso and env.sso.account_id:
            scope = ("aws", env.sso.account_id, env.region)
        else:
            continue  # the account is unknown until sign-in, so nothing to compare against
        for key in ("s3_bucket", "table_prefix"):
            slot = (*scope, key, getattr(env, key))
            if slot in seen:
                raise EnvConfigError(
                    f"{label}: env.{env.name}.{key} = {getattr(env, key)!r} is already used by "
                    f"env.{seen[slot]} in the same account/endpoint"
                )
            seen[slot] = env.name


def _validate(tables: dict[str, dict], default: str, label: str) -> dict[str, Env]:
    envs = {name: _build(name, table, label) for name, table in tables.items()}
    if default not in envs:
        raise EnvConfigError(f"{label}: default = {default!r} names no environment")
    if envs[default].kind != "floci":
        raise EnvConfigError(f"{label}: default = {default!r} must name a floci env")
    _check_collisions(envs, label)
    return envs


def _keep_confirms(committed: dict[str, Env], merged: dict[str, Env], label: str) -> None:
    """The typed confirm is a prod write's only guard, so a personal file may add one, never drop it."""
    for name, env in committed.items():
        if env.confirm and not merged[name].confirm:
            raise EnvConfigError(
                f"{label}: env.{name}.confirm = false would remove the typed confirm that "
                f"{name} requires"
            )


def _guard_confirm_targets(committed: dict[str, Env], merged: dict[str, Env], label: str) -> None:
    """An env reaching a confirm env's bucket or tables must confirm too. A profile env has no
    account for the collision check to compare, so this is what keeps it from aiming at prod."""
    for name, guarded in committed.items():
        if not guarded.confirm:
            continue
        for env in merged.values():
            if env.name == name or env.confirm:
                continue
            for key in ("s3_bucket", "table_prefix"):
                if getattr(env, key) == getattr(guarded, key):
                    raise EnvConfigError(
                        f"{label}: env.{env.name}.{key} = {getattr(env, key)!r} is env.{name}'s, "
                        f"which requires a typed confirm; set confirm = true on env.{env.name}"
                    )


def load_registry(committed: Path, local: Path | None = None) -> Registry:
    raw = _read(committed)
    default = raw.get("default")
    if not isinstance(default, str):
        raise EnvConfigError(f"{committed.name}: missing top-level `default`")
    base = _env_tables(raw, committed.name)
    envs = _validate(base, default, committed.name)

    errors: list[str] = []
    if local is not None and local.exists():
        # The overlay's own `default` is ignored: a personal file must never re-arm the app.
        try:
            over = _env_tables(_read(local), local.name)
            merged = _validate(_merge(base, over), default, local.name)
            _keep_confirms(envs, merged, local.name)
            _guard_confirm_targets(envs, merged, local.name)
            envs = merged
        except EnvConfigError as exc:
            errors.append(f"{exc}; {local.name} was ignored")
    return Registry(default=default, envs=envs, errors=errors)
