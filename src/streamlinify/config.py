from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STREAMLINIFY_")

    workspace_dir: Path = Path("workspace")
    max_per_album: int = 10
    thumb_size: int = 256
    host: str = "127.0.0.1"
    port: int = 8000


settings = Settings()
