from __future__ import annotations

from pydantic_settings import BaseSettings


class KitConfig(BaseSettings):
    """Shared configuration for all Kit packages.

    Reads from environment variables prefixed with KIT_.
    Example: KIT_REDIS_URL=redis://localhost:6379/1
    """

    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    environment: str = "development"
    debug: bool = False

    model_config = {"env_prefix": "KIT_"}

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"
