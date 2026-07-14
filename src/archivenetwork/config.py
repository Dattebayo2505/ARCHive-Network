import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: config.py -> archivenetwork -> src -> <root>. Used to locate vendored binaries.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _default_seven_zip() -> Path | None:
    """Default 7-Zip binary: the committed Windows build on Windows, else None.

    ``vendor/7za.exe`` is a *Windows* executable (and is far faster than Python's
    zipfile on the ~875 MB export). On macOS/Linux it cannot run, so we return
    None and let ``ingest.unzip`` discover a system 7-Zip (``7zz``/``7z``/``7za``)
    or fall back to the stdlib ``zipfile``. Override with ARCHIVENETWORK_SEVEN_ZIP_EXE.
    Must be a zip-capable build — the reduced ``7zr.exe`` cannot read zips.
    """
    if sys.platform.startswith("win"):
        return _PROJECT_ROOT / "vendor" / "7za.exe"
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
