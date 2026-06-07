"""Configuración de la API cargada desde variables de entorno."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración tipada de la API. Lee `.env` del root del repo."""

    # Busca .env en el root del repo (../../.. desde este archivo)
    _root = Path(__file__).resolve().parent.parent.parent.parent.parent  # repos/RepoName
    _env_path = _root / ".env"

    model_config = SettingsConfigDict(
        env_file=_env_path if os.path.exists(_env_path) else ".env",
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

    mysql_app_writer_user: str = Field(default="app_writer")
    mysql_app_writer_password: str = Field(default="")

    cors_origins: str = Field(default="http://localhost:3000")

    jwt_secret: str = Field(default="")
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_ttl_minutes: int = Field(default=15)
    jwt_refresh_ttl_days: int = Field(default=7)

    users_file_path: str = Field(default="users.yaml")

    databricks_host: str = Field(default="")
    databricks_token: str = Field(default="")
    databricks_http_path: str = Field(default="")
    databricks_volume_path: str = Field(default="/Volumes/motoshop/bronze/_landing")

    # ─── DuckDB backend (V1.5) ────────────────────────────────────────
    data_backend: str = Field(default="databricks", description="databricks | duckdb")
    duckdb_path: str = Field(default="/tmp/motoshop_gold.duckdb", description="Path al archivo DuckDB local")

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        if info.data.get("env") == "prod" and (not v or len(v) < 32):
            raise ValueError("jwt_secret debe tener >= 32 caracteres en env=prod")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8"
        )

    @property
    def writer_database_url(self) -> str:
        """URL de conexión para el usuario app_writer (escritura a app_*)."""
        return (
            f"mysql+pymysql://{self.mysql_app_writer_user}:{self.mysql_app_writer_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8"
        )


settings = Settings()
