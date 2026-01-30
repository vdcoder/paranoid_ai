"""Tests for validation module."""

import pytest

from paranoid_ai.models import CleanedData
from paranoid_ai.validation import Validator


@pytest.mark.asyncio
async def test_validator_empty_text():
    """Test validator catches empty cleaned text."""
    validator = Validator()
    cleaned_data = CleanedData(cleaned_text="", extracted_fields={}, confidence=0.9)

    result = await validator.validate(cleaned_data)

    assert not result.is_valid
    assert "empty" in result.errors[0].lower()


@pytest.mark.asyncio
async def test_validator_low_confidence():
    """Test validator warns about low confidence."""
    validator = Validator()
    cleaned_data = CleanedData(
        cleaned_text="Some text", extracted_fields={}, confidence=0.3
    )

    result = await validator.validate(cleaned_data)

    assert len(result.warnings) > 0
    assert "confidence" in result.warnings[0].lower()


@pytest.mark.asyncio
async def test_validator_invalid_email():
    """Test validator catches invalid email format."""
    validator = Validator()
    cleaned_data = CleanedData(
        cleaned_text="Contact info",
        extracted_fields={"email": "not-an-email"},
        confidence=0.9,
    )

    result = await validator.validate(cleaned_data)

    assert not result.is_valid
    assert any("email" in error.lower() for error in result.errors)


@pytest.mark.asyncio
async def test_validator_valid_data():
    """Test validator passes valid data."""
    validator = Validator()
    cleaned_data = CleanedData(
        cleaned_text="Invoice #12345",
        extracted_fields={"invoice_number": "12345", "amount": 100.50},
        confidence=0.95,
    )

    result = await validator.validate(cleaned_data)

    assert result.is_valid
    assert len(result.errors) == 0
