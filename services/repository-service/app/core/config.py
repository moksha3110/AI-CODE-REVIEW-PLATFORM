from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    env: str = Field(default="local")
    log_level: str = Field(default="INFO")
    service_name: str = Field(default="repository-service")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/repository_service"
    )
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=5)

    # --- Redis (webhook delivery dedup fast-path) ---
    redis_url: str = Field(default="redis://localhost:6379/1")
    webhook_dedup_ttl_seconds: int = Field(default=86400)

    # --- JWT verification (shared_auth reads these via env, listed here for clarity) ---
    jwt_public_key_path: str = Field(default="/secrets/jwt/public.pem")
    jwt_issuer: str = Field(default="auth-service")
    jwt_audience: str = Field(default="code-review-platform")

    # --- GitHub App (repo access + webhooks - distinct from the OAuth App in Auth Service) ---
    github_app_id: str = Field(default="")
    github_app_private_key_path: str = Field(default="/secrets/github/app_private_key.pem")
    github_webhook_secret: str = Field(default="")
    github_app_slug: str = Field(default="")  # used to build the installation URL
    installation_token_cache_ttl_seconds: int = Field(default=3300)  # GitHub tokens live 3600s; refresh a bit early

    # --- RabbitMQ ---
    rabbitmq_url: str = Field(default="amqp://guest:guest@localhost:5672/")
    rabbitmq_exchange: str = Field(default="code_review_events")
    outbox_relay_interval_seconds: float = Field(default=1.0)
    outbox_relay_batch_size: int = Field(default=50)

    # --- Internal service-to-service auth (AI Analysis Service calls back for installation tokens) ---
    internal_service_api_key: str = Field(default="change_me_internal_key")

    # --- CORS ---
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # --- Frontend (post-GitHub-App-install redirect target) ---
    frontend_url: str = Field(default="http://localhost:3000")


@lru_cache
def get_settings() -> Settings:
    return Settings()
