import platform
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: config.py -> archivenetwork -> src -> <root>. Used to locate vendored binaries.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _default_seven_zip() -> Path | None:
    """Default 7-Zip binary: resolves the vendored platform/architecture binary.

    - Windows: ``vendor/7za.exe``
    - macOS: ``vendor/7zz_mac`` (Universal Mach-O for Apple Silicon & Intel)
    - Linux x86_64: ``vendor/7zzs_x64``
    - Linux x86 (32-bit): ``vendor/7zzs_x32``
    - Other / ARM Linux: None (falls back to PATH discovery or native tools)
    """
    vendor = _PROJECT_ROOT / "vendor"
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
        elif sys.maxsize > 2**32:
            candidate = vendor / "7zzs_x64"
        else:
            candidate = vendor / "7zzs_x32"

    if candidate is not None and candidate.exists():
        return candidate
    return None


class Settings(BaseSettings):
    # `.env` (gitignored) is where the local Postgres URL lives, so a credential never has to
    # be exported into the shell or committed. Real env vars still win over the file.
    model_config = SettingsConfigDict(
        env_prefix="ARCHIVENETWORK_", env_file=".env", extra="ignore"
    )

    workspace_dir: Path = Path("workspace")
    seven_zip_exe: Path | None = _default_seven_zip()
    max_per_album: int = 10
    thumb_size: int = 512
    preview_size: int = 1280

    # --- Dev-mode: load the built ready/ folder into a local Postgres + local object store. ---
    # Off unless `database_url` is set; every /api/dev/* route 404s without it.
    #
    # `media_root` / `media_base_url` are the *object-store root* — the part before the key.
    # A key begins with "fb-exports/<hashtag>/<album-slug>/" (see loader.storage.media_key).
    # Read URL = <media_base_url>/<storage_path>; in prod that base is a CDN domain instead.
    database_url: str | None = None
    media_root: Path = Path("workspace/store")
    media_base_url: str = "/store"

    # --- S3 upload (on-demand). Independent of dev-mode/Postgres. AWS S3 only. ---
    # Credentials are optional: passed to boto3 only when both are set, else boto3's
    # default credential chain (env / ~/.aws / SSO / instance role) resolves them.
    s3_bucket: str | None = None
    s3_region: str = "ap-southeast-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

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
