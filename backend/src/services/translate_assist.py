"""Translation Assist service for freeform Greek text translation."""

from __future__ import annotations

import json
import logging
import re
import textwrap
from functools import lru_cache
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from services.llm import LLMProvider, get_llm_provider

logger = logging.getLogger(__name__)

CODE_FENCE_REGEX = re.compile(
    r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE
)


class TranslateAssistError(Exception):
    """Raised when the translation assist service cannot fulfill a request."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


class TranslationResult(BaseModel):
    """Response returned to API consumers."""

    source_text: str = Field(..., description="The original Greek text submitted")
    translation: str = Field(..., description="LLM-generated translation suggestion")
    literal_gloss: Optional[str] = Field(
        None, description="Optional literal word-by-word gloss"
    )
    rationale: str = Field(
        ..., description="Explanation of key grammar and vocabulary choices"
    )
    confidence: float = Field(
        0.6, ge=0.0, le=1.0, description="LLM self-rated confidence"
    )
    language: str = Field(default="grc", description="Source language code")


class LLMTranslationResponse(BaseModel):
    """Expected payload from the LLM."""

    translation: str
    rationale: str
    literal_gloss: Optional[str] = None
    confidence: Optional[float] = None


class TranslateAssistService:
    """Service for translating freeform Greek text passages."""

    MAX_TEXT_CHARS = 600  # ~1 paragraph limit

    SYSTEM_PROMPT = (
        "You are Helios, an expert in Classical Greek. "
        "Translate the provided Ancient Greek text into clear, accurate English. "
        "Focus on conveying meaning while noting key grammatical structures."
    )

    def __init__(self, llm_provider: Optional[LLMProvider] = None) -> None:
        self._llm_provider = llm_provider or get_llm_provider()

    async def translate(
        self,
        text: str,
        *,
        language: str = "grc",
    ) -> TranslationResult:
        """Translate Greek text and return structured result."""
        cleaned_text = self._prepare_text(text)

        if not cleaned_text:
            raise TranslateAssistError("Text is empty", status_code=400)

        if len(cleaned_text) > self.MAX_TEXT_CHARS:
            raise TranslateAssistError(
                f"Text exceeds maximum length of {self.MAX_TEXT_CHARS} characters. "
                f"Please select a shorter passage.",
                status_code=400,
            )

        if not self._llm_provider:
            return TranslationResult(
                translation="Contextual translation placeholder.",
                literal_gloss="Literal gloss placeholder.",
                rationale="Demonstration response from mock provider.",
                confidence=0.65,
                source_text=cleaned_text,
            )

        prompt = self._build_prompt(cleaned_text, language)

        try:
            llm_response = await self._llm_provider.suggest_translation(
                prompt, system_prompt=self.SYSTEM_PROMPT
            )
        except Exception as exc:
            logger.exception("LLM provider error: %s", exc)
            raise TranslateAssistError("Unable to reach LLM provider", status_code=502)

        return self._parse_response(
            raw_response=llm_response,
            source_text=cleaned_text,
            language=language,
        )

    def _prepare_text(self, text: str) -> str:
        """Clean and normalize input text."""
        return " ".join(text.split()).strip()

    def _build_prompt(self, text: str, language: str) -> str:
        """Build the prompt for the LLM."""
        lang_name = (
            "Ancient Greek"
            if language == "grc"
            else "Latin"
            if language == "lat"
            else language
        )

        template = f"""
Translate the following {lang_name} text into English.

Return a JSON object with these fields:
- "translation": A clear, readable English translation (max 300 characters)
- "literal_gloss": A more literal word-by-word rendering (optional, can be null)
- "rationale": Brief explanation of key grammar, vocabulary, or interpretive choices
- "confidence": Your confidence in the translation accuracy (0.0 to 1.0)

TEXT TO TRANSLATE:
{text}

JSON RESPONSE:
"""
        return textwrap.dedent(template).strip()

    def _parse_response(
        self,
        *,
        raw_response: str,
        source_text: str,
        language: str,
    ) -> TranslationResult:
        """Parse LLM response into structured result."""
        cleaned = raw_response.strip()

        # Remove markdown code fences if present
        fence_match = CODE_FENCE_REGEX.match(cleaned)
        if fence_match:
            cleaned = fence_match.group(1).strip()

        # Some models prefix with 'json'
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from LLM, returning raw text")
            return TranslationResult(
                source_text=source_text,
                translation=cleaned,
                literal_gloss=None,
                rationale="Raw response from LLM (unable to parse structured JSON).",
                confidence=0.4,
                language=language,
            )

        try:
            normalized = LLMTranslationResponse.model_validate(payload)
        except ValidationError as exc:
            logger.warning("LLM response schema mismatch: %s", exc)
            return TranslationResult(
                source_text=source_text,
                translation=str(payload),
                literal_gloss=None,
                rationale="LLM response did not match expected schema.",
                confidence=0.4,
                language=language,
            )

        confidence = (
            normalized.confidence if normalized.confidence is not None else 0.65
        )
        confidence = max(0.0, min(1.0, confidence))

        return TranslationResult(
            source_text=source_text,
            translation=normalized.translation.strip(),
            literal_gloss=normalized.literal_gloss.strip()
            if normalized.literal_gloss
            else None,
            rationale=normalized.rationale.strip(),
            confidence=confidence,
            language=language,
        )


@lru_cache(maxsize=1)
def get_translate_assist_service() -> TranslateAssistService:
    """FastAPI dependency to obtain a singleton service."""
    return TranslateAssistService()
