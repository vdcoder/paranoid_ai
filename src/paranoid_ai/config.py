"""Configuration management using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Configuration
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # LLM Provider
    llm_provider: Literal["openai", "anthropic"] = Field(
        default="openai", description="LLM provider to use"
    )

    # OpenAI Configuration
    openai_api_key: str | None = Field(default=None, description="OpenAI API key")
    openai_model: str = Field(default="gpt-4-turbo-preview", description="OpenAI model")
    openai_temperature: float = Field(default=0.1, description="OpenAI temperature")

    # Anthropic Configuration
    anthropic_api_key: str | None = Field(default=None, description="Anthropic API key")
    anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022", description="Anthropic model"
    )
    anthropic_temperature: float = Field(default=0.1, description="Anthropic temperature")

    # Application Settings
    max_retries: int = Field(default=3, description="Maximum number of retries")
    timeout_seconds: int = Field(default=30, description="Request timeout in seconds")

    # County Data Settings
    county_data_url: str | None = Field(
        default=None,
        description="Custom URL for county FIPS data (defaults to Census Bureau)"
    )
    county_auto_load: bool = Field(
        default=False,
        description="Automatically load county data on startup"
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
