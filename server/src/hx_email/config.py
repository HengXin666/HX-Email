from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="HX_EMAIL_")

    data_dir: Path = Path("data")
    admin_username: str = "admin"
    admin_password: str = "admin"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "hx_email.sqlite3"
