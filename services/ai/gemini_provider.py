import json
import logging
import os
import re
from typing import Any

from services.ai.errors import (
    AI_AUTHENTICATION_ERROR,
    AI_INVALID_RESPONSE,
    AI_NOT_CONFIGURED,
    AI_PROVIDER_ERROR,
    AI_RATE_LIMIT,
    AI_UNAVAILABLE,
    AIServiceError,
)
from services.ai.provider import AIProvider

try:
    from google import genai
except ImportError:  # pragma: no cover - depends on installed optional SDK
    genai = None


class GeminiProvider(AIProvider):
    MODEL_NAME = "gemini-2.5-flash"

    def __init__(self, api_key=None, client=None):
        self.api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY")
        self.client = client
        self.initialization_error = None
        if self.client is None and self.api_key and genai is not None:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as error:
                self.initialization_error = error
                logging.error("Gemini client initialization failed.")

    def is_configured(self):
        return bool(self.api_key) and self.client is not None

    @staticmethod
    def _parse_json_response(text):
        if not text or not str(text).strip():
            raise AIServiceError(AI_INVALID_RESPONSE, "AI service returned an empty response. Please try again.")

        content = str(text).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"```json\s*(\{.*?\}|\[.*?\])\s*```", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            match = re.search(r"(\{.*\}|\[.*\])", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
        raise AIServiceError(AI_INVALID_RESPONSE, "AI service returned an unexpected response. Please try again.")

    @staticmethod
    def _translate_exception(error):
        message = str(error).lower()
        if "api key" in message or "authentication" in message or "unauthorized" in message or "permission" in message:
            return AIServiceError(
                AI_AUTHENTICATION_ERROR,
                "AI service authentication failed. Please contact the administrator.",
                error,
            )
        if "rate limit" in message or "429" in message or "resource_exhausted" in message:
            return AIServiceError(
                AI_RATE_LIMIT,
                "AI service is temporarily busy. Please try again later.",
                error,
            )
        if any(term in message for term in ("timeout", "network", "connection", "fetch", "unavailable")):
            return AIServiceError(
                AI_UNAVAILABLE,
                "AI service could not be reached. Please try again.",
                error,
            )
        return AIServiceError(
            AI_PROVIDER_ERROR,
            "AI service could not complete the request. Please try again.",
            error,
        )

    def generate_json(self, prompt: str, *, response_schema: Any = None):
        if not self.is_configured():
            if self.api_key:
                raise AIServiceError(
                    AI_PROVIDER_ERROR,
                    "AI service could not be initialized. Please try again later.",
                    self.initialization_error,
                )
            raise AIServiceError(
                AI_NOT_CONFIGURED,
                "AI service is not configured. Please contact the administrator.",
            )

        try:
            request = {
                "model": self.MODEL_NAME,
                "contents": prompt,
            }
            if response_schema is not None:
                request["config"] = {
                    "response_mime_type": "application/json",
                    "response_schema": response_schema,
                }
            response = self.client.models.generate_content(**request)
        except Exception as error:
            translated = self._translate_exception(error)
            logging.error("Gemini request failed (%s).", translated.code)
            raise translated from error

        output = getattr(response, "text", "") or response
        return self._parse_json_response(str(output))
