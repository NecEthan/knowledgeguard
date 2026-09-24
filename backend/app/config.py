import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    secret_key: str = "dev-secret-key-not-for-production"
    cors_origins: str = "http://localhost:3000"

    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/knowledgeguard"
    )

    storage_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket: str = "knowledgeguard"

    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: str = ""
    chat_model: str = "gpt-4o-mini"

    session_cookie_name: str = "kg_session"
    session_max_age_hours: int = 24

    max_upload_size_mb: int = 50


settings = Settings()
