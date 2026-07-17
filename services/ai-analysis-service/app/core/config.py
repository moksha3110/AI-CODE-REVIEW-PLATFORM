from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    env: str = Field(default="local")
    log_level: str = Field(default="INFO")
    service_name: str = Field(default="ai-analysis-service")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/ai_analysis_service"
    )
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=5)

    # --- RabbitMQ ---
    rabbitmq_url: str = Field(default="amqp://guest:guest@localhost:5672/")
    rabbitmq_exchange: str = Field(default="code_review_events")
    rabbitmq_consume_queue: str = Field(default="ai_analysis.analysis_requested")
    rabbitmq_consume_routing_key: str = Field(default="analysis.requested")
    rabbitmq_prefetch_count: int = Field(default=4)
    outbox_relay_interval_seconds: float = Field(default=1.0)
    outbox_relay_batch_size: int = Field(default=50)

    # --- Repository Service (internal API - installation tokens for cloning) ---
    repository_service_base_url: str = Field(default="http://repository-service:8000")
    internal_service_api_key: str = Field(default="change_me_internal_key")

    # --- Git clone limits ---
    clone_timeout_seconds: float = Field(default=30.0)
    max_files_per_push: int = Field(default=25)
    max_file_bytes: int = Field(default=200_000)

    # --- Analysis retry/idempotency ---
    max_analysis_attempts: int = Field(default=3)

    # --- Anthropic (Claude) ---
    anthropic_api_key: str = Field(default="")
    anthropic_model: str = Field(default="claude-opus-4-8")
    anthropic_max_tokens: int = Field(default=4096)


@lru_cache
def get_settings() -> Settings:
    return Settings()
