"""Anthropic LLM provider implementation."""

import json
import re
from typing import Any

import structlog
from anthropic import AsyncAnthropic

from paranoid_ai.config import Settings
from paranoid_ai.llm.base import LLMProvider
from paranoid_ai.llm.prompts import build_system_prompt, build_user_prompt
from paranoid_ai.models import CleanedData

logger = structlog.get_logger()


class AnthropicProvider(LLMProvider):
    """Anthropic implementation of LLM provider."""

    def __init__(self, settings: Settings):
        """Initialize Anthropic provider."""
        if not settings.anthropic_api_key:
            raise ValueError("Anthropic API key is required")

        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model
        self.temperature = settings.anthropic_temperature
        self.max_retries = settings.max_retries

    async def clean_ocr_text(
        self, raw_text: str, context: str | None = None
    ) -> CleanedData:
        """Clean OCR text using Anthropic Claude."""
        logger.info("cleaning_ocr_text", provider="anthropic", text_length=len(raw_text))

        system_prompt = build_system_prompt(context)
        user_prompt = build_user_prompt(raw_text)

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=self.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            content = response.content[0].text
            logger.debug("anthropic_raw_response", content=content[:500])
            
            # Extract JSON from response (handle markdown code blocks)
            json_str = self._extract_json(content)
            result = json.loads(json_str)
            return self._parse_response(result)

        except json.JSONDecodeError as e:
            logger.error("json_parse_error", error=str(e), content=content[:500])
            raise ValueError(f"Failed to parse LLM response as JSON: {e}")
        except Exception as e:
            logger.error("anthropic_error", error=str(e))
            raise

    def _extract_json(self, content: str) -> str:
        """Extract JSON from response, handling markdown code blocks."""
        # Try to find JSON in code blocks first
        code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
        match = re.search(code_block_pattern, content)
        if match:
            return match.group(1).strip()
        
        # Try to find raw JSON object
        json_pattern = r"\{[\s\S]*\}"
        match = re.search(json_pattern, content)
        if match:
            return match.group(0)
        
        # Return original content and let JSON parser handle the error
        return content

    def _parse_response(self, result: dict[str, Any]) -> CleanedData:
        """Parse Anthropic response into CleanedData."""
        return CleanedData(
            cleaned_text=result.get("cleaned_text", ""),
            extracted_fields=result.get("extracted_fields", {}),
            confidence=float(result.get("confidence", 0.9)),
        )
