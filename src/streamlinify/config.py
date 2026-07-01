from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: config.py -> streamlinify -> src -> <root>. Used to locate vendored binaries.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STREAMLINIFY_")

    workspace_dir: Path = Path("workspace")
    # Vendored 7-Zip standalone (decompresses FB exports far faster than Python's zipfile).
    # Must be a zip-capable build (7za.exe / 7z.exe) — the reduced 7zr.exe cannot read zips.
    seven_zip_exe: Path = _PROJECT_ROOT / "vendor" / "7za.exe"
    max_per_album: int = 10
    thumb_size: int = 256
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
