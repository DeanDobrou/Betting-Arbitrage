from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global application settings with environment variable support."""

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "scraper.log"

    # Data paths
    DATA_DIR: str = "data"
    RAW_DATA_DIR: str = "data/raw"
    MATCHED_DATA_DIR: str = "data/matched"
    OPPORTUNITIES_DIR: str = "data/opportunities"

    # Timezone
    TIMEZONE: str = "Europe/Athens"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()
