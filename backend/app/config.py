"""
Meta2bAnalyst - Configuration Settings (Pydantic Settings)
"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Project paths
    PROJECT_ROOT: Path = Path(__file__).resolve().parent
    UPLOAD_DIR: Path = Path("./uploads")
    LOG_DIR: Path = Path("./logs")

    # Database
    DATABASE_URL: str = "sqlite:///./meta2banalyst.db"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # File upload limits
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100MB
    MAX_UPLOAD_FILES: int = 10
    ALLOWED_EXTENSIONS: list[str] = [
        ".csv",
        ".tsv",
        ".txt",
        ".biom",
        ".h5",
        ".shared",
        ".taxonomy",
    ]

    # Application
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # CORS (production should be restricted)
    CORS_ORIGINS: list[str] = ["*"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()

# Ensure directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.LOG_DIR, exist_ok=True)
