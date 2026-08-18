from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT: Path = Path(__file__).resolve().parents[3]
ENV_FILE_PATH: Path = REPOSITORY_ROOT / ".env"
MICROSOFT_MAIL_SCOPE: str = (
    "offline_access https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE_PATH, env_prefix="HX_EMAIL_")

    data_dir: Path = REPOSITORY_ROOT / "data"
    admin_username: str = "admin"
    admin_password: str = "admin"
    secret_key: str = ""
    sync_url: str = ""
    sync_token: str = ""
    sync_interval_seconds: int = 300
    # Docker 自动更新: compose 部署时由环境变量传入 (默认 true), 本地开发默认关闭
    update_enabled: bool = False
    update_compose_dir: str = "/compose"
    update_compose_file: str = ""
    update_image: str = ""
    update_timeout_seconds: int = 900
    # SSRF 守卫策略: 默认放行私网/内网代理与 IMAP 主机 (自托管本机 Clash/V2Ray、
    # LAN 代理、Docker 桥接网关 IP 等), 仅拦截云元数据/link-local/组播等危险保留段;
    # 公网多租户部署可设 HX_EMAIL_ALLOW_PRIVATE_PROXY=false 收紧为白名单
    # (仅 127.0.0.0/8、::1、host.docker.internal 与公网地址)。
    allow_private_proxy: bool = True

    @property
    def database_path(self) -> Path:
        return self.data_dir.resolve() / "hx_email.sqlite3"
