from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # API & infra
    environment: str = "prod"
    log_level: str = "INFO"

    # LLM / ADK related (passed through to sp_agent via env)
    google_api_key: str | None = None
    google_cloud_project: str | None = None
    google_cloud_location: str | None = None

    # Batch processing
    concurrency_limit: int = 80
    # Maximum number of items to process in one logical batch-chunk
    batch_chunk_size: int = 20

    class Config:
        env_prefix = "SP_AGENT_APP_"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()

