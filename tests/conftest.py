"""Pytest configuration and shared fixtures."""
import os
import pytest


@pytest.fixture(autouse=True)
def mock_llm_provider():
    old = os.environ.get("RR_LLM_PROVIDER")
    os.environ["RR_LLM_PROVIDER"] = "mock"
    yield
    if old is not None:
        os.environ["RR_LLM_PROVIDER"] = old
    else:
        os.environ.pop("RR_LLM_PROVIDER", None)