import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
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

    # LLM pricing for cost estimation per query (USD per 1M tokens).
    # Defaults match gpt-4o-mini; override via environment variables.
    llm_input_cost_per_1m_tokens: float = 0.150
    llm_output_cost_per_1m_tokens: float = 0.600

    bcrypt_executor_workers: int = 50
    login_rate_limit: str = "5/minute"

    db_pool_size: int = 30
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800

    # Set to true to skip real OpenAI calls (load testing / CI)
    mock_llm: bool = False


settings = Settings()
