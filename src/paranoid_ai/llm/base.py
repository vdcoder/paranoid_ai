"""Base LLM provider interface."""

from abc import ABC, abstractmethod

from paranoid_ai.models import CleanedData


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def clean_ocr_text(
        self, raw_text: str, context: str | None = None
    ) -> CleanedData:
        """
        Clean OCR text using the LLM.

        Args:
            raw_text: Raw OCR text to clean
            context: Optional context about expected format

        Returns:
            CleanedData with cleaned text and extracted fields
        """
        pass
