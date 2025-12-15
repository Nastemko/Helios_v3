"""LLM provider interfaces and implementations."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract interface for LLM providers used by tutor features."""

    @abstractmethod
    async def suggest_translation(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> str:
        """Return a string response for the provided prompt."""


class OllamaLLMProvider(LLMProvider):
    """LLM provider backed by a local Ollama instance."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout or settings.OLLAMA_TIMEOUT

    async def suggest_translation(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        url = f"{self.base_url}/api/generate"
        logger.debug("Sending prompt to Ollama model %s", self.model)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        text = data.get("response", "")
        if not text:
            logger.warning("Empty response from Ollama")
        return text.strip()


class MockLLMProvider(LLMProvider):
    """Deterministic provider for tests and local development."""

    async def suggest_translation(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> str:
        logger.debug("MockLLMProvider invoked")
        # Return a JSON payload that matches the TutorService schema.
        return (
            '{'
            '"translation": "Contextual translation placeholder.",'
            '"literal_gloss": "Literal gloss placeholder.",'
            '"rationale": "Demonstration response from mock provider.",'
            '"confidence": 0.65'
            '}'
        )


_provider_instance: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    """Return a singleton LLM provider instance."""
    global _provider_instance

    if _provider_instance is None:
        if settings.LLM_ENABLED:
            _provider_instance = OllamaLLMProvider()
            logger.info(
                "Initialized OllamaLLMProvider (model=%s)",
                getattr(_provider_instance, "model", "unknown"),
            )
        else:
            _provider_instance = MockLLMProvider()
            logger.info("Initialized MockLLMProvider because LLM is disabled")

    return _provider_instance


def override_llm_provider(provider: Optional[LLMProvider]) -> None:
    """Override the global provider (primarily for tests)."""
    global _provider_instance
    _provider_instance = provider


