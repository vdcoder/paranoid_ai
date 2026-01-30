"""Pydantic models for request/response validation."""

from typing import Any

from pydantic import BaseModel, Field


class OCRInput(BaseModel):
    """Input model for OCR text cleaning request."""

    raw_text: str = Field(..., description="Raw OCR text to be cleaned", min_length=1)
    context: str | None = Field(
        default=None, description="Optional context about the expected data format"
    )
    validation_rules: dict[str, Any] | None = Field(
        default=None, description="Optional validation rules to apply"
    )


class CountyEnrichment(BaseModel):
    """County FIPS code and tax rate enrichment."""

    state: str | None = Field(default=None, description="State code from document")
    county: str | None = Field(default=None, description="County name from document")
    fips_code: str | None = Field(default=None, description="Resolved FIPS code")
    fips_match_type: str | None = Field(
        default=None, 
        description="Matching strategy: exact, abbreviation_expansion, ai_variation, ai_variation_expanded, fuzzy"
    )
    fips_match_score: int | None = Field(
        default=None, 
        description="Match confidence score (100 for exact, 85-99 for fuzzy)"
    )
    fips_matched_name: str | None = Field(
        default=None, 
        description="The actual county name that matched in Census data"
    )
    tax_rate: float | None = Field(default=None, description="Tax rate for this county")
    enrichment_error: str | None = Field(default=None, description="Error if enrichment failed")


class CleanedData(BaseModel):
    """Cleaned and structured data from LLM."""

    cleaned_text: str = Field(..., description="Cleaned text from LLM")
    extracted_fields: dict[str, Any] = Field(
        default_factory=dict, description="Extracted structured fields"
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence score from LLM"
    )
    county_enrichment: CountyEnrichment | None = Field(
        default=None, description="County FIPS and tax rate enrichment"
    )


class ValidationResult(BaseModel):
    """Result of validation checks."""

    is_valid: bool = Field(..., description="Whether validation passed")
    errors: list[str] = Field(default_factory=list, description="List of validation errors")
    warnings: list[str] = Field(default_factory=list, description="List of validation warnings")


class OCRResponse(BaseModel):
    """Response model for OCR text cleaning."""

    original_text: str = Field(..., description="Original raw OCR text")
    cleaned_data: CleanedData = Field(..., description="Cleaned and structured data")
    validation: ValidationResult = Field(..., description="Validation results")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(default="healthy")
    version: str = Field(...)
    llm_provider: str = Field(...)
