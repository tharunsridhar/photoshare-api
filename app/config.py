"""App configuration, loaded from environment variables (and .env in dev).

DATABASE_URL and JWT_SECRET have no defaults - if they're missing, the app
should fail to boot rather than silently start up with something useless
(or, as this codebase had before, a hardcoded secret committed to git).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- database ---
    database_url: str
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800

    # --- auth (fastapi-users) ---
    jwt_secret: str
    jwt_lifetime_seconds: int = 3600

    # --- media (ImageKit) ---
    imagekit_private_key: str
    imagekit_public_key: str
    imagekit_url: str

    # --- redis (cache + celery broker/result-backend) ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/1"
    feed_cache_ttl_seconds: int = 30
    post_cache_ttl_seconds: int = 60

    # --- cors / deployment ---
    cors_allow_origins: list[str] = ["*"]
    allowed_hosts: list[str] = ["*"]
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
