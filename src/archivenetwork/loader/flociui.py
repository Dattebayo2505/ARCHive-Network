"""Getting the volunteer straight to the bucket, instead of to an interstitial.

`http://<host>:4566/_floci/ui` is a **poller page**, not the UI. floci answers it by creating
and starting the sibling `floci/floci-ui` container on port **4500** through the host
container runtime (this is why `docker-compose.yml` bind-mounts the docker socket), then the
page forwards to it. The destination worth linking to is the storage explorer —
`http://<host>:4500/cloud-explorer/aws/storage` — which is where the uploaded objects
actually are, rather than the console's generic landing page.

The catch, measured against a running floci rather than assumed: **only a GET of the poller
page creates the container.** `/_floci/ui/status` merely reports — polled thirty times against
an absent sidecar it answers `{"ready": false, "url": null}` forever and starts nothing (the
poller page's own script does nothing but poll that endpoint and redirect, so the creation is
a side effect of serving the page). floci also *stops* the sidecar whenever floci itself
restarts, so a warm machine goes cold again on every Restart. On a cold machine port 4500
refuses the connection outright, and a bare deep link would be a dead link — worse than the
interstitial it replaces.

Hence this module: warm first (GET the poller, which does the creating), poll until floci
says ready, and only then hand back the deep link. If it never comes up, hand back the poller
URL instead, because that one always works. The panel therefore shows the deep link in every
normal case and can never show a refused connection.

Everything here is bounded and never raises — an unreachable floci is an *answer*.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

# The UI is a *sibling container* on its own port, so this is deliberately NOT derived from
# the S3 endpoint's port — only its host is shared.
UI_PORT = 4500
EXPLORER_PATH = "/cloud-explorer/aws/storage"
POLLER_PATH = "/_floci/ui"
STATUS_PATH = "/_floci/ui/status"

# The container is pulled and started on first use; a few seconds is normal, and the caller
# runs this in the background on mount so nobody is watching a spinner for it.
DEFAULT_WAIT = 12.0
_REQUEST_TIMEOUT = 5.0
_POLL_INTERVAL = 0.5


@dataclass(frozen=True)
class UiState:
    ready: bool
    url: str  # where to actually send the user: the explorer when up, the poller when not
    explorer: str
    poller: str
    reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "ready": self.ready,
            "url": self.url,
            "explorer": self.explorer,
            "poller": self.poller,
            "reason": self.reason,
        }


def _base(endpoint_url: str) -> tuple[str, str]:
    """Split an S3 endpoint into ('scheme://host:port', 'scheme://host:4500')."""
    parts = urlsplit(endpoint_url or "http://127.0.0.1:4566")
    scheme = parts.scheme or "http"
    host = parts.hostname or "127.0.0.1"
    port = parts.port or (443 if scheme == "https" else 80)
    api = urlunsplit((scheme, f"{host}:{port}", "", "", ""))
    ui = urlunsplit((scheme, f"{host}:{UI_PORT}", "", "", ""))
    return api, ui


def explorer_url(endpoint_url: str) -> str:
    return _base(endpoint_url)[1] + EXPLORER_PATH


def poller_url(endpoint_url: str) -> str:
    return _base(endpoint_url)[0] + POLLER_PATH


def _get(url: str, timeout: float = _REQUEST_TIMEOUT) -> str | None:
    """GET `url`, returning the body or None. Never raises."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - local http
            return response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _status(api_base: str) -> dict | None:
    body = _get(api_base + STATUS_PATH)
    if body is None:
        return None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def ensure(endpoint_url: str, wait: float = DEFAULT_WAIT) -> UiState:
    """Bring the Floci UI up if it isn't, then say where to send the user.

    Idempotent and cheap once the container is running: the first status call short-circuits
    and nothing is started.
    """
    api_base, ui_base = _base(endpoint_url)
    explorer = ui_base + EXPLORER_PATH
    poller = api_base + POLLER_PATH

    first = _status(api_base)
    if first is None:
        # floci itself isn't answering — this is the Docker-down case, already reported by
        # `/api/s3/status`. Don't spend the wait budget on it.
        return UiState(
            ready=False,
            url=poller,
            explorer=explorer,
            poller=poller,
            reason="floci is not answering; the container is probably down.",
        )
    if first.get("ready"):
        return UiState(ready=True, url=explorer, explorer=explorer, poller=poller)

    # Only the poller page creates the sibling container; the status endpoint alone will
    # report `ready: false` forever. Measured, not assumed.
    _get(poller, timeout=_REQUEST_TIMEOUT)

    deadline = time.monotonic() + max(0.0, wait)
    latest: dict | None = first
    while time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL)
        latest = _status(api_base) or latest
        if latest.get("ready"):
            return UiState(ready=True, url=explorer, explorer=explorer, poller=poller)

    return UiState(
        ready=False,
        url=poller,  # always works, even when it has to show its own "starting…" screen
        explorer=explorer,
        poller=poller,
        reason=latest.get("error") or "The Floci UI container hasn't finished starting.",
    )
