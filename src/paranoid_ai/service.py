"""Main service orchestrating OCR cleaning pipeline."""

import time
from typing import Any

import structlog

from paranoid_ai.config import Settings
from paranoid_ai.counties import get_county_lookup
from paranoid_ai.llm import get_llm_provider
from paranoid_ai.models import CleanedData, CountyEnrichment, OCRResponse, ValidationResult
from paranoid_ai.tax_rates import ensure_tax_rates_loaded
from paranoid_ai.validation import Validator

logger = structlog.get_logger()


class OCRCleaningService:
    """Service for cleaning OCR text with LLM and validation."""

    def __init__(self, settings: Settings):
        """Initialize OCR cleaning service."""
        self.settings = settings
        self.llm_provider = get_llm_provider(settings)
        logger.info("service_initialized", llm_provider=settings.llm_provider)

    async def process_ocr_text(
        self,
        raw_text: str,
        context: str | None = None,
        validation_rules: dict[str, Any] | None = None,
    ) -> OCRResponse:
        """
        Process OCR text through the complete pipeline.

        Args:
            raw_text: Raw OCR text to clean
            context: Optional context about expected format
            validation_rules: Optional validation rules to apply

        Returns:
            OCRResponse with cleaned data and validation results
        """
        start_time = time.time()

        logger.info(
            "processing_ocr_text",
            text_length=len(raw_text),
            has_context=context is not None,
            has_rules=validation_rules is not None,
        )

        try:
            # Step 1: Clean text with LLM
            cleaned_data = await self.llm_provider.clean_ocr_text(raw_text, context)

            # Step 2: Enrich with county FIPS and tax rate
            cleaned_data = await self._enrich_county_data(cleaned_data)

            # Step 3: Paranoid validation
            validator = Validator(validation_rules)
            validation_result = await validator.validate(cleaned_data)

            processing_time_ms = (time.time() - start_time) * 1000

            logger.info(
                "processing_complete",
                processing_time_ms=processing_time_ms,
                is_valid=validation_result.is_valid,
            )

            return OCRResponse(
                original_text=raw_text,
                cleaned_data=cleaned_data,
                validation=validation_result,
                processing_time_ms=processing_time_ms,
            )

        except Exception as e:
            logger.error("processing_error", error=str(e))
            raise

    async def _enrich_county_data(self, cleaned_data: CleanedData) -> CleanedData:
        """
        Enrich cleaned data with county FIPS code and tax rate.
        
        Looks up the FIPS code from state+county, then looks up the tax rate.
        """
        fields = cleaned_data.extracted_fields
        state = fields.get("state")
        county = fields.get("county")
        
        if not state or not county:
            logger.debug(
                "county_enrichment_skipped",
                reason="missing state or county",
                state=state,
                county=county,
            )
            return cleaned_data
        
        enrichment = CountyEnrichment(state=state, county=county)
        
        # Get AI-suggested county variations (if provided by LLM)
        ai_variations = fields.get("county_variations", [])
        
        try:
            # Look up FIPS code using multi-layer matching
            county_lookup = get_county_lookup()
            
            if not county_lookup.is_loaded:
                # Try to load county data
                await county_lookup.load()
            
            fips_result = county_lookup.lookup_with_variations(
                state=state,
                county=county,
                ai_variations=ai_variations,  # Pass AI variations!
            )
            
            fips_code = fips_result.get("fips_code")
            enrichment.fips_code = fips_code
            enrichment.fips_match_type = fips_result.get("match_type")
            enrichment.fips_match_score = fips_result.get("match_score")
            enrichment.fips_matched_name = fips_result.get("matched_name")
            
            # Log matching details for debugging/transparency
            if fips_code:
                logger.info(
                    "fips_code_resolved",
                    state=state,
                    county=county,
                    fips_code=fips_code,
                    match_type=enrichment.fips_match_type,
                    match_score=enrichment.fips_match_score,
                    matched_name=enrichment.fips_matched_name,
                    ai_variations_provided=len(ai_variations),
                )
                
                # Look up tax rate
                tax_lookup = ensure_tax_rates_loaded()
                tax_rate = tax_lookup.lookup(fips_code)
                
                if tax_rate is not None:
                    enrichment.tax_rate = tax_rate
                    logger.info(
                        "tax_rate_resolved",
                        fips_code=fips_code,
                        tax_rate=tax_rate,
                    )
                else:
                    logger.warning(
                        "tax_rate_not_found",
                        fips_code=fips_code,
                    )
            else:
                enrichment.enrichment_error = f"FIPS code not found for {county}, {state}"
                logger.warning(
                    "fips_code_not_found",
                    state=state,
                    county=county,
                    variations_tried=fips_result.get("variations_tried"),
                )
                
        except Exception as e:
            enrichment.enrichment_error = str(e)
            logger.error(
                "county_enrichment_error",
                state=state,
                county=county,
                error=str(e),
            )
        
        # Return new CleanedData with enrichment
        return CleanedData(
            cleaned_text=cleaned_data.cleaned_text,
            extracted_fields=cleaned_data.extracted_fields,
            confidence=cleaned_data.confidence,
            county_enrichment=enrichment,
        )
