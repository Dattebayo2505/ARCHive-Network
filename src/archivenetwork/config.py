import platform
import sys
from pathlib import Path

from pydantic import field_validator
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
    # `.env` (gitignored) is where local settings live (the Dev-mode table, S3 credentials), so
    # nothing has to be exported into the shell or committed. Real env vars still win over the file.
    model_config = SettingsConfigDict(
        env_prefix="ARCHIVENETWORK_", env_file=".env", extra="ignore"
    )

    workspace_dir: Path = Path("workspace")
    seven_zip_exe: Path | None = _default_seven_zip()
    max_per_album: int = 10
    thumb_size: int = 512
    preview_size: int = 1280

    # --- Dev-mode: load the built ready/ folder into DynamoDB + a local object store. ---
    # Off unless `dynamodb_table` is set; every /api/dev/* route 404s without it.
    #
    # `media_root` / `media_base_url` are the *object-store root* — the part before the key.
    # A key begins with "fb-exports/<hashtag>/<album-slug>/" (see loader.storage.media_key).
    # Read URL = <media_base_url>/<storage_path>; in prod that base is a CDN domain instead.
    media_root: Path = Path("workspace/store")
    media_base_url: str = "/store"

    # The DynamoDB endpoint is the same floci container as
    # `floci_endpoint_url`; an empty value means real AWS, so it normalises to None. ---
    dynamodb_table: str | None = None
    dynamodb_endpoint_url: str | None = "http://127.0.0.1:4566"

    @field_validator("dynamodb_endpoint_url", mode="before")
    @classmethod
    def _empty_endpoint_is_aws(cls, v):
        return None if v == "" else v

    # --- S3 upload (on-demand). Independent of dev-mode/DynamoDB. AWS S3 only. ---
    # Credentials are optional: passed to boto3 only when both are set, else boto3's
    # default credential chain (env / ~/.aws / SSO / instance role) resolves them.
    s3_bucket: str | None = None
    s3_region: str = "ap-southeast-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    # --- Floci: a local LocalStack-compatible AWS emulator, used as the "testing" upload
    # target. Kept independent of the S3 block on purpose — the switch must work on a machine
    # with no AWS bucket configured, and real credentials must never travel to the emulator.
    # Both fields have defaults, so the testing target is ALWAYS offered; whether the
    # container is actually up is a separate question, answered by storage.probe_endpoint().
    # Region is deliberately NOT duplicated: reusing s3_region keeps the emulator's key
    # layout byte-identical to production's.
    floci_endpoint_url: str = "http://127.0.0.1:4566"
    floci_bucket: str = "archivenetwork-dev"
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


settings = Settings()
