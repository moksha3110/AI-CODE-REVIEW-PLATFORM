from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    env: str = Field(default="local")
    log_level: str = Field(default="INFO")
    service_name: str = Field(default="auth-service")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/auth_service"
    )
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=5)

    # --- Redis (rate limiting + OAuth state storage) ---
    redis_url: str = Field(default="redis://localhost:6379/0")

    # --- JWT ---
    jwt_private_key_path: str = Field(default="/secrets/jwt/private.pem")
    jwt_public_key_path: str = Field(default="/secrets/jwt/public.pem")
    jwt_issuer: str = Field(default="auth-service")
    jwt_audience: str = Field(default="code-review-platform")
    access_token_expire_minutes: int = Field(default=15)
    refresh_token_expire_days: int = Field(default=7)

    # --- GitHub OAuth (user login - distinct from the GitHub App used for repo access) ---
    github_client_id: str = Field(default="")
    github_client_secret: str = Field(default="")
    github_oauth_redirect_uri: str = Field(
        default="http://localhost:8000/api/v1/auth/github/callback"
    )
    github_oauth_scope: str = Field(default="read:user user:email")

    # --- Frontend ---
    frontend_url: str = Field(default="http://localhost:3000")
    frontend_auth_callback_path: str = Field(default="/auth/callback")

    # --- Rate limiting ---
    login_rate_limit_per_minute: int = Field(default=10)
    oauth_state_ttl_seconds: int = Field(default=600)

    # --- CORS ---
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
