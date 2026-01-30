"""OpenAI LLM provider implementation."""

import json
from typing import Any

import structlog
from openai import AsyncOpenAI

from paranoid_ai.config import Settings
from paranoid_ai.llm.base import LLMProvider
from paranoid_ai.llm.prompts import build_system_prompt, build_user_prompt
from paranoid_ai.models import CleanedData

logger = structlog.get_logger()


class OpenAIProvider(LLMProvider):
    """OpenAI implementation of LLM provider."""

    def __init__(self, settings: Settings):
        """Initialize OpenAI provider."""
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key is required")

        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.temperature = settings.openai_temperature
        self.max_retries = settings.max_retries

    async def clean_ocr_text(
        self, raw_text: str, context: str | None = None
    ) -> CleanedData:
        """Clean OCR text using OpenAI."""
        logger.info("cleaning_ocr_text", provider="openai", text_length=len(raw_text))

        system_prompt = build_system_prompt(context)
        user_prompt = build_user_prompt(raw_text)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from OpenAI")

            result = json.loads(content)
            return self._parse_response(result)

        except Exception as e:
            logger.error("openai_error", error=str(e))
            raise

    def _parse_response(self, result: dict[str, Any]) -> CleanedData:
        """Parse OpenAI response into CleanedData."""
        return CleanedData(
            cleaned_text=result.get("cleaned_text", ""),
            extracted_fields=result.get("extracted_fields", {}),
            confidence=float(result.get("confidence", 0.9)),
        )
