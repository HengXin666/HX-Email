from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HX_EMAIL_")

    data_dir: Path = Path(".data")

    @property
    def database_path(self) -> Path:
        return self.data_dir / "hx_email.sqlite3"
