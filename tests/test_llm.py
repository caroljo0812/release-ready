"""Test the LLM client with mock provider."""
import pytest
from release_ready.llm import chat, mock_response, LLMConfig


def test_mock_response():
    r = mock_response("test content", model="test-model", provider="test")
    assert r.content == "test content"
    assert r.usage.total > 0
    assert r.provider_info["effective_provider"] == "mock"


def test_llm_config_defaults():
    cfg = LLMConfig()
    assert cfg.provider == "mimo"
    assert cfg.model == "mimo-v2.5-pro"
    assert cfg.max_tokens == 1200


def test_chat_mock_no_key():
    # Without API key, should gracefully return or raise
    import os
    old_key = os.environ.pop("RR_LLM_API_KEY", None)
    old_prov = os.environ.get("RR_LLM_PROVIDER", "mimo")
    os.environ["RR_LLM_PROVIDER"] = "mock"
    try:
        r = chat([{"role": "user", "content": "hi"}], provider="mock", api_key=None)
        assert r.content == ""
    finally:
        os.environ["RR_LLM_PROVIDER"] = old_prov
        if old_key:
            os.environ["RR_LLM_API_KEY"] = old_key
