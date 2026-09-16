from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    secret_key: str = "dev-secret-key-not-for-production"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/knowledgeguard"

    storage_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket: str = "knowledgeguard"

    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: str = ""


settings = Settings()
