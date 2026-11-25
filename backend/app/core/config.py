
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# ============================================
# FlowDesk Settings
# ============================================

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # MySQL 閰嶇疆

    mysql_host: str = Field(
        default="127.0.0.1",
        min_length=1,
    )

    mysql_port: int = Field(
        default=3306,
        ge=1,
        le=65535,
    )

    mysql_user: str = Field(
        default="root",
        min_length=1,
    )

    mysql_password: SecretStr = Field(
        min_length=1,
    )

    mysql_database: str = Field(
        default="flowdesk_init_test",
        min_length=1,
    )

    mysql_charset: str = "utf8mb4"

    # JWT 閰嶇疆

    jwt_secret_key: SecretStr = Field(
        min_length=32,
    )

    jwt_access_token_expire_minutes: int = Field(
        default=30,
        ge=1,
    )


settings = Settings()

