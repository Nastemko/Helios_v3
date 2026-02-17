"""LLM provider interfaces and implementations."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from functools import lru_cache

from openai import AsyncOpenAI
from openai.types import Reasoning
from openai.types.shared.reasoning_effort import ReasoningEffort
from pydantic import BaseModel

from config import ThinkLevel, settings

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract interface for LLM providers used by tutor features."""

    @abstractmethod
    async def suggest_translation(
        self,
        prompt: str,
        *,
        system_prompt: str,
        response_model: BaseModel,
    ) -> BaseModel | None:
        """Return a string response for the provided prompt."""


class OllamaLLMProvider(LLMProvider):
    """LLM provider backed by a local Ollama instance (via OpenAI-compatible API)."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
        temperature: float | None = None,
        think: str | None = None,
    ) -> None:
        base_url = (base_url or settings.llm.BASE_URL).rstrip("/")
        self.model = model or settings.llm.MODEL
        self.temperature = temperature or settings.llm.TEMPERATURE
        self.think = think or settings.llm.THINK

        # Initialize OpenAI client with configured endpoint
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or settings.llm.API_KEY,
            timeout=timeout or settings.llm.TIMEOUT,
        )

    async def suggest_translation(
        self,
        prompt: str,
        *,
        system_prompt: str,
        response_model: BaseModel,
    ) -> BaseModel | None:
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Add user prompt
        messages.append({"role": "user", "content": prompt})

        logger.debug("Sending prompt to Ollama model %s via OpenAI API", self.model)

        response = await self.client.responses.parse(
            model=self.model,
            input=messages,
            temperature=self.temperature,
            reasoning=Reasoning(effort=self.think) if self.think else None,
            text_format=response_model,
        )

        return response.output_parsed


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
