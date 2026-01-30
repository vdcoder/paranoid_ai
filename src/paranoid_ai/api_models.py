"""Pydantic configuration and models for Paranoid AI."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
    anthropic_api_key: str | None = Field(default=None)
    anthropic_model: str = Field(default="claude-sonnet-4-20250514")
    anthropic_temperature: float = Field(default=0.1)

    @property
    def llm_provider(self) -> str:
        return "anthropic"

@lru_cache
def get_settings() -> Settings:
    return Settings()

class OCRInput(BaseModel):
    """Input for OCR text cleaning."""
    raw_text: str = Field(..., min_length=1)
    context: str | None = None
    validation_rules: dict[str, Any] | None = None

class CountyEnrichment(BaseModel):
    """County FIPS code and tax rate enrichment data."""
    state: str | None = None
    county: str | None = None
    fips_code: str | None = None
    fips_match_type: str | None = None
    fips_match_score: int | None = None
    fips_matched_name: str | None = None
    tax_rate: float | None = None
    enrichment_error: str | None = None

class CleanedData(BaseModel):
    """Cleaned and structured data from LLM."""
    cleaned_text: str
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    county_enrichment: CountyEnrichment | None = None

class ValidationResult(BaseModel):
    """Result of paranoid validation checks."""
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class OCRResponse(BaseModel):
    """Response from OCR cleaning endpoint."""
    original_text: str
    cleaned_data: CleanedData
    validation: ValidationResult
    processing_time_ms: float

class CountyLookupRequest(BaseModel):
    state: str = Field(..., min_length=2, max_length=2)
    county: str
    ai_variations: list[str] | None = None

    @field_validator("state")
    @classmethod
    def normalize_state(cls, v: str) -> str:
        return v.upper().strip()

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str
    llm_provider: str
