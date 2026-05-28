"""Configuración de la API cargada desde variables de entorno."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración tipada de la API. Lee `.env` por defecto."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    env: str = Field(default="dev")

    mysql_host: str = Field(default="localhost")
    mysql_port: int = Field(default=3306)
    mysql_database: str = Field(default="motoshop2024")
    mysql_user: str = Field(default="api_read")
    mysql_password: str = Field(default="")

    cors_origins: str = Field(default="http://localhost:3000")

    jwt_secret: str = Field(default="")
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_ttl_minutes: int = Field(default=15)
    jwt_refresh_ttl_days: int = Field(default=7)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
