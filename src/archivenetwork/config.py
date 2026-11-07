import platform
import re
import sys
from collections.abc import Mapping
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: config.py -> archivenetwork -> src -> <root>. Used to locate vendored binaries
# and the checked-in docker-compose.yml (see loader/dockerctl.py).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _default_seven_zip() -> Path | None:
    """Default 7-Zip binary: resolves the vendored platform/architecture binary.

    - Windows: ``vendor/7za.exe``
    - macOS: ``vendor/7zz_mac`` (Universal Mach-O for Apple Silicon & Intel)
    - Linux x86_64: ``vendor/7zzs_x64``
    - Linux x86 (32-bit): ``vendor/7zzs_x32``
    - Other / ARM Linux: None (falls back to PATH discovery or native tools)

    Note: The vendored Linux binaries (``7zzs_x64``, ``7zzs_x32``) are x86 binaries
    and are NOT compatible with ARM architectures (such as Linux ``aarch64``,
    ``arm64``, ``armv7l``, ``riscv64``). On non-x86 Linux, this returns None so
    extraction falls back to system tools on PATH or Python stdlib ``zipfile``.
    """
    vendor = PROJECT_ROOT / "vendor"
    candidate: Path | None = None
    if sys.platform.startswith("win"):
        candidate = vendor / "7za.exe"
    elif sys.platform == "darwin":
        candidate = vendor / "7zz_mac"
    elif sys.platform.startswith("linux"):
        machine = platform.machine().lower()
        if machine in ("x86_64", "amd64"):
            candidate = vendor / "7zzs_x64"
        elif machine in ("i386", "i686", "x86"):
            candidate = vendor / "7zzs_x32"
        # Non-x86 Linux architectures (aarch64, arm64, armv7l, riscv64, etc.) are not
        # compatible with vendored x86 binaries, so candidate remains None.

    if candidate is not None and candidate.exists():
        return candidate
    return None


class Settings(BaseSettings):
    # `.env` (gitignored, optional) holds machine settings only; every one has a default. AWS and
    # floci targets live in environments.toml / environments.local.toml. Real env vars still win.
    model_config = SettingsConfigDict(
        env_prefix="ARCHIVENETWORK_", env_file=".env", extra="ignore"
    )

    workspace_dir: Path = Path("workspace")
    # Named environments (loader/envs.py): the committed file plus a gitignored overlay.
    environments_file: Path = PROJECT_ROOT / "environments.toml"
    environments_local_file: Path = PROJECT_ROOT / "environments.local.toml"
    seven_zip_exe: Path | None = _default_seven_zip()
    max_per_album: int = 10
    thumb_size: int = 512
    preview_size: int = 1280

    # Log at startup whether floci is the latest release (loader/flociversion.py). It makes
    # one GitHub call, so switch it off (ARCHIVENETWORK_FLOCI_VERSION_CHECK=false) when offline.
    floci_version_check: bool = True

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    # Both servers are local, but Vite falls back to :5174/:5175/… when :5173 is
    # taken. Allow any localhost / 127.0.0.1 port so a port bump never breaks CORS.
    cors_origin_regex: str = r"http://(localhost|127\.0\.0\.1)(:\d+)?"


# Settings that moved to environments.toml / environments.local.toml. Still present in `.env` or
# the environment, they are reported by name so nobody believes they are being read.
STALE_KEYS: tuple[str, ...] = tuple(
    "ARCHIVENETWORK_" + name.upper()
    for name in (
        "dynamodb_table_prefix",
        "dynamodb_table",
        "dynamodb_endpoint_url",
        "s3_bucket",
        "s3_region",
        "s3_access_key_id",
        "s3_secret_access_key",
        "floci_endpoint_url",
        "floci_bucket",
        "media_root",
        "media_base_url",
    )
)
_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def stale_settings(env_file: Path, environ: Mapping[str, str]) -> list[str]:
    """Sorted names of retired settings set in `environ` or as `NAME=` lines in `env_file`.

    Names only: the values may be credentials, so they never leave this function.
    """
    found = {k for k in STALE_KEYS if k in environ}
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        lines = []
    for line in lines:
        m = _ENV_LINE.match(line)
        if m and m.group(1).upper() in STALE_KEYS:
            found.add(m.group(1).upper())
    return sorted(found)


settings = Settings()
