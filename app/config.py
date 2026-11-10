"""
SledgeCO-AI: Configuration module.

Loads settings from environment variables / .env file using Pydantic BaseSettings.
All configuration is centralized here — no hardcoded values elsewhere.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root directory (parent of app/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM Provider ---
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    model_name: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model ID for extraction",
    )
    llm_provider: Literal["anthropic", "mock"] = Field(
        default="mock",
        description="LLM provider to use: 'anthropic' for production, 'mock' for testing",
    )

    # --- Pipeline ---
    max_file_size_mb: int = Field(default=50, ge=1, le=500)
    min_text_chars_per_page: int = Field(default=50, ge=0)
    scan_render_dpi: int = Field(default=300, ge=72, le=600)
    ocr_language: str = Field(default="eng")
    ocr_timeout_seconds: int = Field(default=60, ge=1, le=300)
    tesseract_cmd: str = Field(
        default="",
        description="Optional explicit path to the Tesseract executable",
    )

    # --- Confidence ---
    enable_multi_run: bool = Field(default=False)
    num_extraction_runs: int = Field(default=3, ge=1, le=5)

    # --- Logging ---
    log_level: str = Field(default="INFO")
    log_document_text: bool = Field(
        default=False,
        description="SECURITY: When False, document text is never logged",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is a valid Python logging level name."""
        v = v.upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v not in valid_levels:
            raise ValueError(f"Invalid log level '{v}'. Must be one of: {valid_levels}")
        return v

    @property
    def max_file_size_bytes(self) -> int:
        """Maximum file size in bytes."""
        return self.max_file_size_mb * 1024 * 1024

    def get_log_level(self) -> int:
        """Return the numeric logging level."""
        return getattr(logging, self.log_level)


def get_settings() -> Settings:
    """
    Factory function for Settings.

    Uses a simple cache to avoid re-reading .env on every call.
    In tests, create Settings() directly with overrides.
    """
    return Settings()


def setup_logging(settings: Settings | None = None) -> None:
    """
    Configure application-wide logging.

    Security: When log_document_text is False, a filter is applied
    to prevent document content from appearing in logs.
    """
    if settings is None:
        settings = get_settings()

    logging.basicConfig(
        level=settings.get_log_level(),
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
