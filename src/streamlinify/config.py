import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: config.py -> streamlinify -> src -> <root>. Used to locate vendored binaries.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _default_seven_zip() -> Path | None:
    """Default 7-Zip binary: the committed Windows build on Windows, else None.

    ``vendor/7za.exe`` is a *Windows* executable (and is far faster than Python's
    zipfile on the ~875 MB export). On macOS/Linux it cannot run, so we return
    None and let ``ingest.unzip`` discover a system 7-Zip (``7zz``/``7z``/``7za``)
    or fall back to the stdlib ``zipfile``. Override with STREAMLINIFY_SEVEN_ZIP_EXE.
    Must be a zip-capable build — the reduced ``7zr.exe`` cannot read zips.
    """
    if sys.platform.startswith("win"):
        return _PROJECT_ROOT / "vendor" / "7za.exe"
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STREAMLINIFY_")

    workspace_dir: Path = Path("workspace")
    seven_zip_exe: Path | None = _default_seven_zip()
    max_per_album: int = 10
    thumb_size: int = 512
    preview_size: int = 1280
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
