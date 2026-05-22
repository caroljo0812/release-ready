"""OpenAI-compatible LLM client with JSON repair and MiMo default."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

LLM_MAPPING = {
    "mimo": "https://api.xiaomimimo.com/v1",
    "openai": "https://api.openai.com/v1",
    "together": "https://api.together.xyz/v1",
}

DEFAULT_PROVIDER = os.environ.get("RR_LLM_PROVIDER", "mimo")
DEFAULT_MODEL = os.environ.get("RR_LLM_MODEL", "mimo-v2.5-pro")


@dataclass
class LLMConfig:
    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int = 1200
    temperature: float = 0.3

    @property
    def effective_provider(self) -> str:
        if self.base_url:
            return "custom"
        return self.provider


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMResponse:
    content: str
    usage: Usage
    provider_info: dict[str, Any]
    raw: dict[str, Any]


def _client(provider: str, api_key: str | None, base_url: str | None) -> httpx.Client:
    if base_url:
        base = base_url
    elif provider in LLM_MAPPING:
        base = LLM_MAPPING[provider]
    else:
        base = provider
    headers = {}
    key = api_key or os.environ.get("RR_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return httpx.Client(base_url=base, headers=headers, timeout=60.0)


def _json_repair(text: str) -> str:
    text = text.strip()
    for start in range(len(text)):
        if text[start] in ("{", "["):
            break
    text = text[start:]
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    # Try stripping trailing commas
    fixed = text
    for _ in range(3):
        try:
            json.loads(fixed)
            return fixed
        except json.JSONDecodeError:
            pass
        fixed = _strip_trailing_comma(fixed)
    # Try wrapping in array
    try:
        json.loads(f"[{fixed}]")
        return f"[{fixed}]"
    except json.JSONDecodeError:
        pass
    return text


def _strip_trailing_comma(text: str) -> str:
    import re
    return re.sub(r",(\s*[}\]])", r"\1", text)


def chat(
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    provider: str = DEFAULT_PROVIDER,
    api_key: str | None = None,
    base_url: str | None = None,
    max_tokens: int = 1200,
    temperature: float = 0.3,
    json_mode: bool = False,
) -> LLMResponse:
    # Short-circuit mock provider — no HTTP needed
    effective = provider if provider in LLM_MAPPING else ("mock" if provider == "mock" else "custom")
    if effective == "mock":
        return LLMResponse(
            content="",
            usage=Usage(prompt_tokens=0, completion_tokens=0),
            provider_info={
                "configured_provider": provider,
                "configured_model": model,
                "effective_provider": "mock",
                "base_url": None,
            },
            raw={},
        )

    client = _client(provider, api_key, base_url)

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    for attempt in range(3):
        try:
            resp = client.post("/chat/completions", json=payload)
            if resp.status_code == 429 or resp.status_code >= 500:
                import time
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            raw = resp.json()
            break
        except httpx.HTTPStatusError:
            raise
        except Exception:
            import time
            time.sleep(2 ** attempt)
            continue

    choices = raw.get("choices", [])
    content = choices[0]["message"]["content"] if choices else ""

    usage_data = raw.get("usage", {})
    usage = Usage(
        prompt_tokens=usage_data.get("prompt_tokens", 0),
        completion_tokens=usage_data.get("completion_tokens", 0),
    )
    return LLMResponse(
        content=content,
        usage=usage,
        provider_info={
            "configured_provider": provider,
            "configured_model": model,
            "effective_provider": effective,
            "base_url": client.base_url,
        },
        raw=raw,
    )


def structured(
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    model: str = DEFAULT_MODEL,
    provider: str = DEFAULT_PROVIDER,
    api_key: str | None = None,
    base_url: str | None = None,
    max_tokens: int = 1500,
) -> tuple[dict[str, Any], LLMResponse]:
    """Call chat with JSON-mode schema constraint, repair if needed."""
    system_msg = messages[0] if messages else {}
    wrapped = [{"role": "system",
                "content": f"{system_msg.get('content', '')}\n\nYou must respond with ONLY a valid JSON object matching this schema:\n{json.dumps(schema)}"}] + messages[1:]

    resp = chat(wrapped, model=model, provider=provider, api_key=api_key,
                base_url=base_url, max_tokens=max_tokens, json_mode=True)

    raw_text = resp.content
    # Try to extract JSON from markdown code blocks
    import re
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw_text)
    if m:
        raw_text = m.group(1)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        repaired = _json_repair(raw_text)
        try:
            parsed = json.loads(repaired)
        except json.JSONDecodeError:
            logging.warning("JSON repair failed, returning empty list")
            parsed = []

    return parsed, resp


def mock_response(content: str, model: str = "mock", provider: str = "mock") -> LLMResponse:
    return LLMResponse(
        content=content,
        usage=Usage(prompt_tokens=50, completion_tokens=len(content.split())),
        provider_info={
            "configured_provider": provider,
            "configured_model": model,
            "effective_provider": "mock",
        },
        raw={},
    )
