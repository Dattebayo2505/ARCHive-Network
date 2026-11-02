"""Is the local floci the latest release?

Compares three readings:
- **running**: what the container says it is (`/_floci/health` → `version`);
- **pinned**: the `image: floci/floci:<tag>` line in the checked-in `docker-compose.yml`;
- **latest**: GitHub's newest non-prerelease (`releases/latest`).

Why it exists: compose never re-pulls an image it already has, so a floating `latest` tag let
this machine sit on floci 1.7.0 for two months, a release that drops every DynamoDB table with a
sorted GSI on restart (fixed in 2.0.0). The pin makes the version explicit, and this check says
when the pin or the container has fallen behind. The app logs it once at startup
(`app._lifespan`), and `GET /api/docker/floci-version` returns it on demand.

Everything here is bounded and never raises: an unreachable floci or GitHub is an *answer*.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

LATEST_URL = "https://api.github.com/repos/floci-io/floci/releases/latest"
HEALTH_PATH = "/_floci/health"
_TIMEOUT = 3.0
# Unauthenticated GitHub allows 60 calls an hour; a release a week needs nothing fresher.
_LATEST_TTL = 3600.0
_latest_cache: dict[str, tuple[float, str | None]] = {}

_IMAGE_LINE = re.compile(r"^\s*image:\s*floci/floci:(\S+)", re.MULTILINE)
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")

Status = Literal["up_to_date", "update_available", "mismatch", "not_pinned", "unknown"]


@dataclass(frozen=True)
class VersionReport:
    running: str | None
    pinned: str | None
    latest: str | None
    status: Status
    message: str

    def as_dict(self) -> dict:
        return {
            "running": self.running,
            "pinned": self.pinned,
            "latest": self.latest,
            "status": self.status,
            "message": self.message,
        }


def parse(version: str | None) -> tuple[int, int, int] | None:
    """`2.4.0`, `v2.4.0` and `2.4.0-compat` → (2, 4, 0); `latest`, `nightly`, None → None."""
    match = _VERSION.match(version or "")
    return tuple(int(part) for part in match.groups()) if match else None


def _get(url: str, timeout: float = _TIMEOUT) -> str | None:
    """GET `url`, returning the body or None. Never raises."""
    request = urllib.request.Request(url, headers={"User-Agent": "archivenetwork"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _json_field(body: str | None, field: str) -> str | None:
    try:
        value = json.loads(body or "").get(field)
    except (json.JSONDecodeError, AttributeError):
        return None
    return value if isinstance(value, str) else None


def running_version(endpoint_url: str) -> str | None:
    return _json_field(_get(endpoint_url.rstrip("/") + HEALTH_PATH), "version")


def pinned_version(compose_file: Path) -> str | None:
    try:
        match = _IMAGE_LINE.search(compose_file.read_text(encoding="utf-8"))
    except OSError:
        return None
    return match.group(1) if match else None


def latest_version() -> str | None:
    cached = _latest_cache.get(LATEST_URL)
    if cached and time.monotonic() - cached[0] < _LATEST_TTL:
        return cached[1]
    tag = _json_field(_get(LATEST_URL), "tag_name")
    latest = tag.removeprefix("v") if tag else None
    _latest_cache[LATEST_URL] = (time.monotonic(), latest)
    return latest


def assess(running: str | None, pinned: str | None, latest: str | None) -> VersionReport:
    """Pure: turn the three readings into one status and a one-line, actionable message."""
    rv, pv, lv = parse(running), parse(pinned), parse(latest)
    state = f"running {running}" if running else "not running"

    def report(status: Status, message: str) -> VersionReport:
        return VersionReport(running, pinned, latest, status, message)

    if pv is None:
        return report("not_pinned", f"docker-compose.yml uses floci/floci:{pinned}, which compose "
                      "never re-pulls. Pin a version (e.g. floci/floci:"
                      f"{latest or '<version>'}).")
    if rv is not None and rv != pv:
        return report("mismatch", f"floci {running} is running, but docker-compose.yml pins "
                      f"{pinned}. Run `docker compose pull && docker compose up -d`.")
    if lv is None:
        return report("unknown", f"floci {pinned} pinned ({state}); couldn't reach GitHub for "
                      "the latest release.")
    if pv < lv:
        return report("update_available", f"floci {latest} is out; docker-compose.yml pins "
                      f"{pinned} ({state}). Bump the image tag, then run "
                      "`docker compose pull && docker compose up -d`.")
    return report("up_to_date", f"floci {pinned} is the latest release ({state}).")


def report(endpoint_url: str, compose_file: Path) -> VersionReport:
    return assess(running_version(endpoint_url), pinned_version(compose_file), latest_version())
