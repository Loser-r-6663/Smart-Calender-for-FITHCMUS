"""Small adapter around google-genai; no SDK import occurs at module import time."""

from typing import Any, Protocol
import random
import time

from .config import GeminiConfig
from .errors import (ProviderAuthenticationError, ProviderError, ProviderEmptyResponseError,
                     ProviderPermissionError, ProviderRequestError, ProviderSchemaError)
from .extraction_schema import ExtractionEnvelope, parse_envelope


class GeminiGateway(Protocol):
    def extract(self, prompt: str) -> Any: ...


class GeminiClient:
    def __init__(self, config: GeminiConfig | None = None, sdk_client: Any = None) -> None:
        self.config = config or GeminiConfig.from_env()
        injected = sdk_client is not None
        if sdk_client is None:
            try:
                from google import genai
                sdk_client = genai.Client(api_key=self.config.api_key, http_options={"timeout": int(self.config.timeout_seconds * 1000)})
            except ImportError as exc:
                raise ProviderError("google-genai is not installed") from exc
        if not injected and not self.config.api_key:
            raise ProviderError("GEMINI_API_KEY is required for a real Gemini client")
        self._client = sdk_client

    def extract(self, prompt: str) -> Any:
        if len(prompt) > self.config.max_input_chars:
            raise ProviderRequestError("Gemini input exceeds configured limit")
        last: Exception | None = None
        for attempt in range(self.config.retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.config.model,
                    contents=prompt,
                    config={
                        "temperature": self.config.temperature,
                        "max_output_tokens": self.config.max_output_tokens,
                        "response_mime_type": "application/json",
                        "response_schema": ExtractionEnvelope,
                    },
                )
                parsed = getattr(response, "parsed", None)
                if parsed is not None:
                    try:
                        return parse_envelope(parsed)
                    except Exception as exc:
                        raise ProviderSchemaError("Gemini response did not match the extraction schema") from exc
                text = getattr(response, "text", None)
                if not text:
                    raise ProviderEmptyResponseError("Gemini returned an empty response")
                import json
                try:
                    return parse_envelope(json.loads(text))
                except Exception as exc:
                    raise ProviderSchemaError("Gemini response did not match the extraction schema") from exc
            except ProviderError:
                raise
            except Exception as exc:
                last = exc
                status = getattr(exc, "status_code", getattr(exc, "code", None))
                if status == 401:
                    raise ProviderAuthenticationError("Gemini authentication failed") from exc
                if status == 403:
                    raise ProviderPermissionError("Gemini permission denied") from exc
                transient = status == 429 or (isinstance(status, int) and status >= 500) or isinstance(exc, TimeoutError)
                if not transient or attempt >= self.config.retries:
                    raise ProviderRequestError("Gemini request failed") from exc
                time.sleep(min(8.0, 0.5 * (2 ** attempt)) + random.random() * 0.25)
        raise ProviderRequestError("Gemini request failed") from last
