"""Factory for creating LLM providers."""

from paranoid_ai.config import Settings
from paranoid_ai.llm.anthropic_provider import AnthropicProvider
from paranoid_ai.llm.base import LLMProvider
from paranoid_ai.llm.openai_provider import OpenAIProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    """
    Factory function to get the appropriate LLM provider.

    Args:
        settings: Application settings

    Returns:
        LLM provider instance

    Raises:
        ValueError: If unsupported provider is specified
    """
    providers = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
    }

    provider_class = providers.get(settings.llm_provider)
    if not provider_class:
        raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")

    return provider_class(settings)
