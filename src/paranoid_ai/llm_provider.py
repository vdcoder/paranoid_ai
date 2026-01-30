"""Anthropic Claude LLM provider for OCR text cleaning."""

import json
import re

import structlog
from anthropic import AsyncAnthropic

from paranoid_ai.api_models import CleanedData, Settings

logger = structlog.get_logger()

EXAMPLE_OCR_INPUT = """*** RECORDING REQ ***
Doc: DEED-TRUST-0042
County: S. Clara  |  State: CA
Date Signed: 2024-01-15
Date Recorded: 2024-01-10
Grantor:  T.E.S.L.A. Holdings LLC
Grantee:  John  &  Sarah  Connor
Amount: $1,250,000.00 (One Million Two Hundred Thousand Dollars)
APN: 992-001-XA
Status: PRELIMINARY
*** END ***"""

EXAMPLE_OCR_OUTPUT = """{
    "cleaned_text": "*** RECORDING REQ ***\\nDoc: DEED-TRUST-0042\\nCounty: S. Clara | State: CA\\nDate Signed: 2024-01-15\\nDate Recorded: 2024-01-10\\nGrantor: T.E.S.L.A. Holdings LLC\\nGrantee: John & Sarah Connor\\nAmount: $1,250,000.00 (One Million Two Hundred Fifty Thousand Dollars)\\nAPN: 992-001-XA\\nStatus: PRELIMINARY\\n*** END ***",
    "extracted_fields": {
        "document_type": "DEED-TRUST",
        "document_number": "0042",
        "county": "Santa Clara",
        "county_variations": ["Santa Clara", "St. Clara", "Sta Clara", "Sta. Clara"],
        "state": "CA",
        "date_signed": "2024-01-15",
        "date_recorded": "2024-01-10",
        "grantor": "T.E.S.L.A. Holdings LLC",
        "grantee": "John & Sarah Connor",
        "amount_numeric": 1250000.00,
        "amount_original_text": "One Million Two Hundred Thousand Dollars",
        "amount_corrected_text": "One Million Two Hundred Fifty Thousand Dollars",
        "amount_parsed_by_ai": 1250000,
        "amount_has_discrepancy": true,
        "apn": "992-001-XA",
        "status": "PRELIMINARY"
    },
    "confidence": 0.85
}"""

SYSTEM_PROMPT = f"""You are an expert OCR text cleaner specializing in legal and financial documents. Your task is to:

1. **Fix OCR Errors**: Correct common OCR misreads (O vs 0, I vs 1 vs l, S vs 5, etc.)

2. **Normalize Formatting**: Fix spacing, expand abbreviations when clear

3. **Extract Structured Fields**: Parse key-value pairs, dates in ISO format (YYYY-MM-DD)

4. **County Name Handling** (for FIPS lookup):
   - `county`: Your best interpretation (expanded, e.g., "Santa Clara")
   - `county_variations`: 2-5 possible variations for Census Bureau matching

5. **Amount Handling** (for paranoid validation):
   - `amount_numeric`: The numeric value from the document
   - `amount_original_text`: EXACT text as it appears in OCR
   - `amount_corrected_text`: Your corrected version if text doesn't match number
   - `amount_parsed_by_ai`: Your interpretation of the original text as a number
   - `amount_has_discrepancy`: true if amount_numeric != amount_parsed_by_ai

## Example

Input:
```
{EXAMPLE_OCR_INPUT}
```

Output:
```json
{EXAMPLE_OCR_OUTPUT}
```

Return ONLY a valid JSON object with: cleaned_text, extracted_fields, confidence (0.0-1.0)."""


class AnthropicProvider:
    """Anthropic Claude implementation for OCR cleaning."""

    def __init__(self, settings: Settings):
        if not settings.anthropic_api_key:
            raise ValueError("Anthropic API key is required")
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model
        self.temperature = settings.anthropic_temperature

    async def clean_ocr_text(self, raw_text: str, context: str | None = None) -> CleanedData:
        """Clean OCR text using Anthropic Claude."""
        logger.info("cleaning_ocr_text", provider="anthropic", text_length=len(raw_text))

        system = SYSTEM_PROMPT + (f"\n\n## Additional Context\n{context}" if context else "")
        user = f"Clean and extract data from this OCR text:\n\n```\n{raw_text}\n```"

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=self.temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )

            content = response.content[0].text
            json_str = self._extract_json(content)
            result = json.loads(json_str)

            return CleanedData(
                cleaned_text=result.get("cleaned_text", ""),
                extracted_fields=result.get("extracted_fields", {}),
                confidence=float(result.get("confidence", 0.9)),
            )

        except json.JSONDecodeError as e:
            logger.error("json_parse_error", error=str(e))
            raise ValueError(f"Failed to parse LLM response as JSON: {e}")
        except Exception as e:
            logger.error("anthropic_error", error=str(e))
            raise

    def _extract_json(self, content: str) -> str:
        """Extract JSON from response, handling markdown code blocks."""
        match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", content)
        if match:
            return match.group(1).strip()
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            return match.group(0)
        return content


def get_llm_provider(settings: Settings) -> AnthropicProvider:
    """Get the Anthropic LLM provider."""
    return AnthropicProvider(settings)
