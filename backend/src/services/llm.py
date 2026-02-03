"""LLM provider interfaces and implementations."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from functools import lru_cache

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
        temperature: float | None = None,
        think: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.llm.BASE_URL).rstrip("/")
        self.model = model or settings.llm.MODEL
        self.timeout = timeout or settings.llm.TIMEOUT
        self.temperature = temperature or settings.llm.TEMPERATURE
        self.think = think or settings.llm.THINK

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
            "think": self.think,
            "options": {
                "temperature": self.temperature,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        url = f"{self.base_url}/api/generate"
        logger.debug("Sending prompt to Ollama model %s", self.model)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        text: str = data.get("response", "")
        if not text:
            logger.warning("Empty response from Ollama")
        return text.strip()


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider | None:
    """Return a singleton LLM provider instance."""
    if not settings.llm.ENABLED:
        return
    _provider_instance = OllamaLLMProvider()
    logger.info(
        "Initialized OllamaLLMProvider (model=%s)",
        _provider_instance.model,
    )

    return _provider_instance
