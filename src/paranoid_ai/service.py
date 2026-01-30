"""Main service with paranoid validation - verifies AI output with deterministic code."""

import re
import time
from datetime import datetime
from typing import Any

import structlog
from text_to_num import text2num

from paranoid_ai.counties import get_county_lookup
from paranoid_ai.llm_provider import get_llm_provider
from paranoid_ai.api_models import CleanedData, CountyEnrichment, OCRResponse, Settings, ValidationResult
from paranoid_ai.tax_rates import ensure_tax_rates_loaded

logger = structlog.get_logger()


class Validator:
    """Paranoid validator: trust the AI, but verify with code."""

    def __init__(self, rules: dict[str, Any] | None = None):
        self.rules = rules or {}

    async def validate(self, data: CleanedData) -> ValidationResult:
        """Run all paranoid validation checks."""
        errors: list[str] = []
        warnings: list[str] = []
        fields = data.extracted_fields

        if not data.cleaned_text.strip():
            errors.append("VALIDATED WITH CODE > Cleaned text is empty")

        if data.confidence < 0.5:
            warnings.append(f"VALIDATED WITH CODE > Low confidence score: {data.confidence:.2f}")

        amt_err, amt_warn = self._check_amounts(fields)
        errors.extend(amt_err)
        warnings.extend(amt_warn)
        errors.extend(self._check_date_logic(fields))
        errors.extend(self._check_date_formats(fields))
        errors.extend(self._check_county(data))
        errors.extend(self._check_fields(fields))

        if self.rules:
            errors.extend(self._apply_rules(data))

        warnings.extend(self._check_patterns(data.cleaned_text))

        logger.info("validation_complete", is_valid=len(errors) == 0, errors=len(errors))
        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _check_amounts(self, fields: dict[str, Any]) -> tuple[list[str], list[str]]:
        """Cross-validate numeric amount against text representation."""
        errors, warnings = [], []

        amount = fields.get("amount_numeric") or fields.get("amount")
        original_text = fields.get("amount_original_text") or fields.get("amount_text")
        corrected_text = fields.get("amount_corrected_text")
        ai_parsed = fields.get("amount_parsed_by_ai")
        has_discrepancy = fields.get("amount_has_discrepancy", False)

        if amount is None:
            errors.append(
                f"VALIDATED WITH CODE > AMOUNT MISSING ERROR: Missing amount value. "
                f"Cannot validate without amount!"
            )
            return errors, warnings

        if has_discrepancy:
            warnings.append(
                f"VALIDATED WITH AI > AI DETECTED DISCREPANCY: '{original_text}' doesn't match ${amount:,.2f}. "
                f"AI parsed as ${ai_parsed:,.2f}, corrected to '{corrected_text}'."
            )

        if original_text:
            our_parsed = self._parse_text_amount(original_text)
            if our_parsed is not None and our_parsed != amount:
                errors.append(
                    f"VALIDATED WITH CODE > AMOUNT MISMATCH: Text '{original_text}' parses to ${our_parsed:,.2f} "
                    f"but document shows ${amount:,.2f}. Possible OCR error or tampering."
                )

        if corrected_text:
            corrected_parsed = self._parse_text_amount(corrected_text)
            if corrected_parsed is not None and corrected_parsed != amount:
                errors.append(
                    f"VALIDATED WITH CODE > CORRECTED TEXT MISMATCH: '{corrected_text}' parses to ${corrected_parsed:,.2f}, "
                    f"should be ${amount:,.2f}."
                )

        return errors, warnings

    def _parse_text_amount(self, text: str) -> int | None:
        """Parse written amount ('One Million') to integer using text2num."""
        if not text:
            return None

        normalized = text.lower()
        normalized = re.sub(r"[^a-z\s]", "", normalized)
        normalized = re.sub(r"\b(dollars?|cents?|and)\b", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()

        if not normalized:
            return None

        try:
            return int(text2num(normalized, lang="en"))
        except ValueError:
            return None

    def _check_date_logic(self, fields: dict[str, Any]) -> list[str]:
        """Verify recording date >= signing date."""
        errors = []
        signed, recorded = fields.get("date_signed"), fields.get("date_recorded")

        if not signed or not recorded:
            errors.append(
                f"VALIDATED WITH CODE > DATE MISSING ERROR: Missing signed or recorded date. "
                f"Cannot record before signing!"
            )
            return errors

        try:
            if datetime.fromisoformat(signed) > datetime.fromisoformat(recorded):
                errors.append(
                    f"VALIDATED WITH CODE > DATE LOGIC ERROR: Signed {signed} but recorded {recorded}. "
                    f"Cannot record before signing!"
                )
        except ValueError as e:
            errors.append(f"VALIDATED WITH CODE > DATE PARSE ERROR: {e}")
        return errors

    def _check_date_formats(self, fields: dict[str, Any]) -> list[str]:
        """Verify date strings are valid and reasonable."""
        errors = []

        for field in ["date_signed", "date_recorded"]:
            date_str = fields.get(field)
            if not date_str:
                continue

            try:
                dt = datetime.fromisoformat(date_str)
                if dt.year < 1900:
                    errors.append(f"VALIDATED WITH CODE > SUSPICIOUS DATE: {field} year {dt.year} seems too old.")
                if dt.year > datetime.now().year + 1:
                    errors.append(f"VALIDATED WITH CODE > FUTURE DATE ERROR: {field} is {date_str}, in the future.")
            except ValueError:
                errors.append(f"VALIDATED WITH CODE > INVALID DATE FORMAT: {field} '{date_str}' is not a valid date.")
        return errors

    def _check_county(self, data: CleanedData) -> list[str]:
        """Verify county exists in Census Bureau data."""
        errors = []
        enrichment = data.county_enrichment

        if enrichment and enrichment.county and enrichment.state and not enrichment.fips_code:
            errors.append(
                f"VALIDATED WITH CODE > UNRECOGNIZED COUNTY: '{enrichment.county}' in '{enrichment.state}' not found in Census data. "
                f"Tried exact, abbreviation, AI variations, and fuzzy matching (80% threshold)."
            )

        return errors

    def _check_fields(self, fields: dict[str, Any]) -> list[str]:
        """Basic field validation."""
        errors = []

        for key, value in fields.items():
            if isinstance(value, (int, float)) and value < 0 and "amount" in key.lower():
                errors.append(f"VALIDATED WITH CODE > Field '{key}' has negative value: {value}")

            if "email" in key.lower() and isinstance(value, str):
                if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", value):
                    errors.append(f"VALIDATED WITH CODE > Field '{key}' has invalid email format: {value}")

        return errors

    def _apply_rules(self, data: CleanedData) -> list[str]:
        """Apply custom validation rules."""
        errors = []

        for field in self.rules.get("required_fields", []):
            if field not in data.extracted_fields:
                errors.append(f"VALIDATED WITH CODE > Required field '{field}' is missing")

        for field, pattern in self.rules.get("field_patterns", {}).items():
            if field in data.extracted_fields:
                if not re.match(pattern, str(data.extracted_fields[field])):
                    errors.append(f"VALIDATED WITH CODE > Field '{field}' doesn't match pattern: {pattern}")

        return errors

    def _check_patterns(self, text: str) -> list[str]:
        """Check for suspicious OCR patterns."""
        warnings = []

        if re.search(r"[Il1|]{3,}", text):
            warnings.append("VALIDATED WITH CODE > Detected suspicious sequence of similar characters (I, l, 1, |)")
        if re.search(r"\s{5,}", text):
            warnings.append("VALIDATED WITH CODE > Detected unusual spacing (5+ consecutive spaces)")
        if text.endswith("...") or text.endswith("…"):
            warnings.append("VALIDATED WITH CODE > Text appears to be truncated")

        return warnings


class OCRCleaningService:
    """Orchestrates OCR cleaning: LLM extraction → County enrichment → Paranoid validation."""

    def __init__(self, settings: Settings):
        self.llm_provider = get_llm_provider(settings)
        logger.info("service_initialized", llm_provider=settings.llm_provider)

    async def process_ocr_text(
        self,
        raw_text: str,
        context: str | None = None,
        validation_rules: dict[str, Any] | None = None,
    ) -> OCRResponse:
        """Process OCR text: clean with LLM, enrich with FIPS/tax, validate paranoid-style."""
        start_time = time.time()
        logger.info("processing_ocr_text", text_length=len(raw_text))

        cleaned_data = await self.llm_provider.clean_ocr_text(raw_text, context)
        cleaned_data = await self._enrich_county_data(cleaned_data)
        validation = await Validator(validation_rules).validate(cleaned_data)

        processing_time_ms = (time.time() - start_time) * 1000
        logger.info("processing_complete", processing_time_ms=processing_time_ms, is_valid=validation.is_valid)

        return OCRResponse(
            original_text=raw_text,
            cleaned_data=cleaned_data,
            validation=validation,
            processing_time_ms=processing_time_ms,
        )

    async def _enrich_county_data(self, cleaned_data: CleanedData) -> CleanedData:
        """Enrich with FIPS code and tax rate via multi-layer county matching."""
        fields = cleaned_data.extracted_fields
        state, county = fields.get("state"), fields.get("county")

        if not state or not county:
            return cleaned_data

        enrichment = CountyEnrichment(state=state, county=county)
        ai_variations = fields.get("county_variations", [])

        try:
            county_lookup = get_county_lookup()
            if not county_lookup.is_loaded:
                await county_lookup.load()

            result = county_lookup.lookup_with_variations(state, county, ai_variations)
            fips_code = result.get("fips_code")

            enrichment.fips_code = fips_code
            enrichment.fips_match_type = result.get("match_type")
            enrichment.fips_match_score = result.get("match_score")
            enrichment.fips_matched_name = result.get("matched_name")

            if fips_code:
                logger.info("fips_resolved", fips=fips_code, match=result.get("match_type"))
                tax_rate = ensure_tax_rates_loaded().lookup(fips_code)
                if tax_rate:
                    enrichment.tax_rate = tax_rate
            else:
                enrichment.enrichment_error = f"FIPS not found for {county}, {state}"

        except Exception as e:
            enrichment.enrichment_error = str(e)
            logger.error("enrichment_error", error=str(e))

        return CleanedData(
            cleaned_text=cleaned_data.cleaned_text,
            extracted_fields=cleaned_data.extracted_fields,
            confidence=cleaned_data.confidence,
            county_enrichment=enrichment,
        )
