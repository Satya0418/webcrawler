"""
Application configuration and settings.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    DEBUG: bool = False
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    CORS_ORIGINS: list = ["http://localhost:3000", "http://localhost:8000"]

    # Database (PostgreSQL in production, SQLite fallback for dev/testing)
    DATABASE_URL: str = "sqlite:///./medicine_safety.db"
    DATABASE_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # FDA Source
    FDA_BASE_URL: str = "https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges"
    FDA_CRAWL_TIMEOUT: int = 30  # seconds
    FDA_CRAWL_RETRIES: int = 3
    FDA_CRAWL_BACKOFF_FACTOR: float = 0.3

    # Cache
    CACHE_TTL: int = 3600  # 1 hour in seconds

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Logging
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True


# Create global settings instance
settings = Settings()
