from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    env: str = Field(default="local")
    log_level: str = Field(default="INFO")
    service_name: str = Field(default="notification-service")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/notification_service"
    )
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=5)

    # --- RabbitMQ ---
    rabbitmq_url: str = Field(default="amqp://guest:guest@localhost:5672/")
    rabbitmq_exchange: str = Field(default="code_review_events")
    rabbitmq_consume_queue: str = Field(default="notification_service.review_completed")
    rabbitmq_consume_routing_key: str = Field(default="review.completed")
    rabbitmq_prefetch_count: int = Field(default=8)

    # --- Repository Service (internal API - resolve repo owner to notify) ---
    repository_service_base_url: str = Field(default="http://repository-service:8000")
    internal_service_api_key: str = Field(default="change_me_internal_key")

    # --- JWT verification (shared_auth reads these via env, listed here for clarity) ---
    jwt_public_key_path: str = Field(default="/secrets/jwt/public.pem")
    jwt_issuer: str = Field(default="auth-service")
    jwt_audience: str = Field(default="code-review-platform")

    # --- Pagination ---
    default_page_size: int = Field(default=20)
    max_page_size: int = Field(default=100)

    # --- CORS ---
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
