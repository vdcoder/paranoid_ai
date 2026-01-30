"""Pytest configuration and fixtures."""

import pytest
from fastapi.testclient import TestClient

from paranoid_ai.api import app
from paranoid_ai.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings."""
    return Settings(
        api_debug=True,
        llm_provider="openai",
        openai_api_key="test-key",
        log_level="DEBUG",
    )


@pytest.fixture
def test_client() -> TestClient:
    """Create test client for FastAPI app."""
    return TestClient(app)
