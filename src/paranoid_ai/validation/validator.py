"""Validation logic for cleaned OCR data - PARANOID MODE."""

import re
from datetime import datetime
from typing import Any

import structlog
from text_to_num import text2num

from paranoid_ai.models import CleanedData, ValidationResult

logger = structlog.get_logger()


class Validator:
    """Validator for PARANOID validation of cleaned OCR data.
    
    This validator doesn't just trust the AI - it verifies everything with code.
    We use multiple sources of truth to catch discrepancies.
    """

    def __init__(self, validation_rules: dict[str, Any] | None = None):
        """
        Initialize validator with optional custom rules.

        Args:
            validation_rules: Dictionary of validation rules to apply
        """
        self.validation_rules = validation_rules or {}

    async def validate(self, cleaned_data: CleanedData) -> ValidationResult:
        """
        Perform PARANOID validation on cleaned data.
        
        We verify the AI's work with actual code - trust but verify!

        Args:
            cleaned_data: Cleaned data from LLM

        Returns:
            ValidationResult with validation status and any errors/warnings
        """
        logger.info("paranoid_validation_starting")

        errors: list[str] = []
        warnings: list[str] = []

        fields = cleaned_data.extracted_fields

        # Basic sanity checks
        if not cleaned_data.cleaned_text.strip():
            errors.append("Cleaned text is empty")

        # Check confidence threshold
        if cleaned_data.confidence < 0.5:
            warnings.append(f"Low confidence score: {cleaned_data.confidence:.2f}")

        # ===========================================
        # PARANOID CHECK #1: Amount Validation (Multi-Source)
        # ===========================================
        amount_errors, amount_warnings = self._validate_amounts_paranoid(fields)
        errors.extend(amount_errors)
        warnings.extend(amount_warnings)

        # ===========================================
        # PARANOID CHECK #2: Date Logic Validation
        # ===========================================
        date_errors = self._validate_date_logic(fields)
        errors.extend(date_errors)

        # ===========================================
        # PARANOID CHECK #3: Verify AI's date parsing
        # ===========================================
        date_parse_errors = self._verify_dates_are_valid(fields)
        errors.extend(date_parse_errors)

        # ===========================================
        # PARANOID CHECK #4: County Validation (FIPS lookup)
        # ===========================================
        county_errors = self._validate_county_paranoid(cleaned_data)
        errors.extend(county_errors)

        # Validate extracted fields (basic checks)
        field_errors = self._validate_extracted_fields(fields)
        errors.extend(field_errors)

        # Apply custom validation rules
        if self.validation_rules:
            custom_errors = self._apply_custom_rules(cleaned_data)
            errors.extend(custom_errors)

        # Check for suspicious patterns
        suspicious_warnings = self._check_suspicious_patterns(cleaned_data.cleaned_text)
        warnings.extend(suspicious_warnings)

        is_valid = len(errors) == 0

        logger.info(
            "paranoid_validation_complete",
            is_valid=is_valid,
            errors=len(errors),
            warnings=len(warnings),
            error_details=errors,
        )

        return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)

    def _validate_amounts_paranoid(self, fields: dict[str, Any]) -> tuple[list[str], list[str]]:
        """
        PARANOID CHECK: Multi-source amount validation.
        
        We have up to 4 sources of truth:
        1. amount_numeric: The numeric value from document (e.g., $1,250,000.00)
        2. amount_original_text: The OCR text as-is
        3. amount_corrected_text: AI's corrected text
        4. amount_parsed_by_ai: AI's interpretation of the original text
        5. Our own parsing of the original text (using text2num)
        
        If these don't agree, something is wrong!
        """
        errors = []
        warnings = []
        
        # Get all amount fields
        amount_numeric = fields.get("amount_numeric")
        amount_original_text = fields.get("amount_original_text")
        amount_corrected_text = fields.get("amount_corrected_text")
        amount_parsed_by_ai = fields.get("amount_parsed_by_ai")
        amount_has_discrepancy = fields.get("amount_has_discrepancy", False)
        
        # Fallback to old field names for backward compatibility
        if amount_numeric is None:
            amount_numeric = fields.get("amount")
        if amount_original_text is None:
            amount_original_text = fields.get("amount_text")
        
        # Log what we're working with
        logger.debug(
            "amount_validation_inputs",
            amount_numeric=amount_numeric,
            amount_original_text=amount_original_text,
            amount_corrected_text=amount_corrected_text,
            amount_parsed_by_ai=amount_parsed_by_ai,
            amount_has_discrepancy=amount_has_discrepancy,
        )
        
        if amount_numeric is None:
            # Can't validate without a numeric amount
            return errors, warnings
        
        # ===== Check 1: AI detected discrepancy =====
        if amount_has_discrepancy:
            warnings.append(
                f"AI DETECTED DISCREPANCY: The original text '{amount_original_text}' "
                f"does not match the numeric amount ${amount_numeric:,.2f}. "
                f"AI parsed original as ${amount_parsed_by_ai:,.2f} and corrected to '{amount_corrected_text}'."
            )
        
        # ===== Check 2: Our own parsing of original text =====
        if amount_original_text:
            our_parsed_amount = self._parse_amount_text(amount_original_text)
            
            if our_parsed_amount is not None:
                if our_parsed_amount != amount_numeric:
                    errors.append(
                        f"AMOUNT MISMATCH (Code Verification): Original text '{amount_original_text}' "
                        f"parses to ${our_parsed_amount:,.2f}, but document shows ${amount_numeric:,.2f}. "
                        f"This indicates OCR error or data tampering."
                    )
                    logger.warning(
                        "amount_mismatch_code_verified",
                        amount_numeric=amount_numeric,
                        original_text=amount_original_text,
                        our_parsed=our_parsed_amount,
                    )
                    
                # Also compare with AI's parsing
                if amount_parsed_by_ai is not None and our_parsed_amount != amount_parsed_by_ai:
                    warnings.append(
                        f"PARSING DISAGREEMENT: Our parser got ${our_parsed_amount:,.2f} "
                        f"but AI parsed as ${amount_parsed_by_ai:,.2f} from '{amount_original_text}'. "
                        f"Manual review recommended."
                    )
        
        # ===== Check 3: Verify corrected text matches numeric =====
        if amount_corrected_text:
            corrected_parsed = self._parse_amount_text(amount_corrected_text)
            
            if corrected_parsed is not None and corrected_parsed != amount_numeric:
                errors.append(
                    f"CORRECTED TEXT MISMATCH: AI's corrected text '{amount_corrected_text}' "
                    f"parses to ${corrected_parsed:,.2f}, but should be ${amount_numeric:,.2f}."
                )
        
        return errors, warnings

    def _parse_amount_text(self, text: str) -> int | None:
        """
        Parse written amount text into a number using text2num library.
        
        Uses text2num which supports multiple languages (English, French, Spanish, etc.)
        and handles complex number expressions reliably.
        
        Examples:
            "One Million Two Hundred Fifty Thousand Dollars" -> 1250000
            "Five Hundred Thousand" -> 500000
            "Two Hundred Fifty" -> 250
        """
        if not text:
            return None
        
        # Normalize text - remove currency words and punctuation
        normalized = text.lower()
        normalized = re.sub(r"[^a-z\s]", "", normalized)  # Remove non-letters
        normalized = re.sub(r"\s+", " ", normalized).strip()  # Normalize spaces
        
        # Remove common currency suffixes (word boundaries to avoid "thousand" -> "thous")
        normalized = re.sub(r"\bdollars?\b", "", normalized)
        normalized = re.sub(r"\bcents?\b", "", normalized)
        normalized = re.sub(r"\band\b", "", normalized)  # "one hundred and fifty" -> "one hundred fifty"
        normalized = re.sub(r"\s+", " ", normalized).strip()
        
        if not normalized:
            return None
        
        try:
            # Use text2num library - supports multiple languages!
            parsed_value = text2num(normalized, lang="en")
            
            logger.debug(
                "amount_text_parsed",
                original_text=text,
                normalized_text=normalized,
                parsed_value=parsed_value,
            )
            
            return int(parsed_value)
            
        except ValueError as e:
            logger.warning(
                "text2num_parse_failed",
                text=text,
                normalized=normalized,
                error=str(e),
            )
            return None

    def _validate_date_logic(self, fields: dict[str, Any]) -> list[str]:
        """
        PARANOID CHECK: Verify date logic makes sense.
        
        A document cannot be recorded before it is signed!
        """
        errors = []
        
        date_signed = fields.get("date_signed")
        date_recorded = fields.get("date_recorded")
        
        if not date_signed or not date_recorded:
            return errors
        
        try:
            signed_dt = datetime.fromisoformat(date_signed)
            recorded_dt = datetime.fromisoformat(date_recorded)
            
            if signed_dt > recorded_dt:
                errors.append(
                    f"DATE LOGIC ERROR: Document was signed on {date_signed} but "
                    f"recorded on {date_recorded}. A document cannot be recorded "
                    f"before it is signed! This indicates OCR error or fraud."
                )
                logger.warning(
                    "date_logic_error",
                    date_signed=date_signed,
                    date_recorded=date_recorded,
                )
        except ValueError as e:
            errors.append(f"DATE PARSE ERROR: Could not parse dates for validation: {e}")
        
        return errors

    def _verify_dates_are_valid(self, fields: dict[str, Any]) -> list[str]:
        """
        PARANOID CHECK: Verify that date strings are actually valid dates.
        
        Don't trust the AI's parsing - verify with code.
        """
        errors = []
        
        date_fields = ["date_signed", "date_recorded"]
        
        for field_name in date_fields:
            date_str = fields.get(field_name)
            if not date_str:
                continue
            
            try:
                # Try to parse the date
                parsed_date = datetime.fromisoformat(date_str)
                
                # Check for obviously wrong dates
                if parsed_date.year < 1900:
                    errors.append(
                        f"SUSPICIOUS DATE: {field_name} has year {parsed_date.year}, "
                        f"which seems too old for a modern document."
                    )
                
                if parsed_date.year > datetime.now().year + 1:
                    errors.append(
                        f"FUTURE DATE ERROR: {field_name} is {date_str}, "
                        f"which is in the future. Documents cannot be dated in the future."
                    )
                    
            except ValueError:
                errors.append(
                    f"INVALID DATE FORMAT: {field_name} value '{date_str}' is not a valid date."
                )
        
        return errors

    def _validate_county_paranoid(self, cleaned_data: CleanedData) -> list[str]:
        """
        PARANOID CHECK: Verify county is valid via FIPS lookup.
        
        If a county is provided but we can't find it in Census Bureau data
        (even with fuzzy matching!), it's likely invalid or fake.
        
        This is a critical validation - you can't just make up county names!
        """
        errors = []
        
        enrichment = cleaned_data.county_enrichment
        if enrichment is None:
            # No enrichment data - can't validate
            return errors
        
        county = enrichment.county
        state = enrichment.state
        
        if not county or not state:
            # No county/state provided - nothing to validate
            return errors
        
        # Check if we could resolve a FIPS code
        if enrichment.fips_code is None:
            # We have a county but couldn't find it!
            errors.append(
                f"UNRECOGNIZED COUNTY: '{county}' in state '{state}' could not be found in Census data. "
                f"Tried exact match, abbreviation expansion, AI variations, and fuzzy matching (80% threshold). "
                f"This may indicate an invalid, misspelled, or fabricated county name."
            )
            
            logger.warning(
                "county_validation_failed",
                county=county,
                state=state,
                error=enrichment.enrichment_error,
                reason="unrecognized_county",
            )
        
        return errors

    def _validate_extracted_fields(self, fields: dict[str, Any]) -> list[str]:
        """Validate extracted fields for common issues."""
        errors = []

        for key, value in fields.items():
            # Check for numeric fields
            if isinstance(value, (int, float)):
                if value < 0 and "amount" in key.lower():
                    errors.append(f"Field '{key}' has negative value: {value}")

            # Check for date fields
            if "date" in key.lower() and isinstance(value, str):
                if not self._is_valid_date_format(value):
                    errors.append(f"Field '{key}' has invalid date format: {value}")

            # Check for email fields
            if "email" in key.lower() and isinstance(value, str):
                if not self._is_valid_email(value):
                    errors.append(f"Field '{key}' has invalid email format: {value}")

        return errors

    def _apply_custom_rules(self, cleaned_data: CleanedData) -> list[str]:
        """Apply custom validation rules."""
        errors = []

        # Example: Check required fields
        required_fields = self.validation_rules.get("required_fields", [])
        for field in required_fields:
            if field not in cleaned_data.extracted_fields:
                errors.append(f"Required field '{field}' is missing")

        # Example: Check field patterns
        field_patterns = self.validation_rules.get("field_patterns", {})
        for field, pattern in field_patterns.items():
            if field in cleaned_data.extracted_fields:
                value = str(cleaned_data.extracted_fields[field])
                if not re.match(pattern, value):
                    errors.append(f"Field '{field}' doesn't match pattern: {pattern}")

        return errors

    def _check_suspicious_patterns(self, text: str) -> list[str]:
        """Check for suspicious patterns in cleaned text."""
        warnings = []

        # Check for mixed character sets that might indicate OCR errors
        if re.search(r"[Il1|]{3,}", text):
            warnings.append("Detected suspicious sequence of similar characters (I, l, 1, |)")

        # Check for unusual spacing
        if re.search(r"\s{5,}", text):
            warnings.append("Detected unusual spacing (5+ consecutive spaces)")

        # Check for truncated text indicators
        if text.endswith("...") or text.endswith("…"):
            warnings.append("Text appears to be truncated")

        return warnings

    @staticmethod
    def _is_valid_date_format(date_str: str) -> bool:
        """Check if string matches common date formats."""
        date_patterns = [
            r"\d{4}-\d{2}-\d{2}",  # YYYY-MM-DD
            r"\d{2}/\d{2}/\d{4}",  # MM/DD/YYYY
            r"\d{2}-\d{2}-\d{4}",  # DD-MM-YYYY
        ]
        return any(re.match(pattern, date_str) for pattern in date_patterns)

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        """Basic email validation."""
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, email))
