from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT: Path = Path(__file__).resolve().parents[3]
ENV_FILE_PATH: Path = REPOSITORY_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE_PATH, env_prefix="HX_EMAIL_")

    data_dir: Path = REPOSITORY_ROOT / "data"
    admin_username: str = "admin"
    admin_password: str = "admin"
    secret_key: str = ""

    @property
    def database_path(self) -> Path:
        return self.data_dir.resolve() / "hx_email.sqlite3"
