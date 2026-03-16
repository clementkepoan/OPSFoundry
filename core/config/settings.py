from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OPSFoundry API"
    app_env: str = "local"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    postgres_db: str = "opsfoundry"
    postgres_user: str = "opsfoundry"
    postgres_password: str = "opsfoundry"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    redis_url: str = "redis://redis:6379/0"
    duplicate_request_ttl_seconds: int = 15
    storage_root: Path = Path("storage")
    database_url: str | None = None
    mlflow_tracking_uri: str | None = None
    mlflow_experiment_name: str = "opsfoundry"
    frontend_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @computed_field
    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def document_storage_dir(self) -> Path:
        return self.storage_root / "documents"

    @property
    def work_item_storage_dir(self) -> Path:
        return self.storage_root / "work_items"

    @property
    def audit_storage_dir(self) -> Path:
        return self.storage_root / "audit"

    @property
    def export_storage_dir(self) -> Path:
        return self.storage_root / "exports"

    @property
    def mlflow_storage_dir(self) -> Path:
        return self.storage_root / "mlruns"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
