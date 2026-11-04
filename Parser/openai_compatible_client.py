"""Minimal OpenAI Chat Completions compatible HTTP client."""

import json
import random
import socket
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import OpenAICompatibleConfig
from .errors import (
    ProviderAuthenticationError,
    ProviderEmptyResponseError,
    ProviderPermissionError,
    ProviderRequestError,
    ProviderSchemaError,
)
from .extraction_schema import parse_envelope, provider_schema
from .llm_gateway import LLMGateway


def chat_completions_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    return value + "/chat/completions"


class OpenAICompatibleClient:
    def __init__(
        self,
        config: OpenAICompatibleConfig | None = None,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        self.config = config or OpenAICompatibleConfig.from_env()
        if not self.config.api_key:
            raise ProviderRequestError("OPENAI_API_KEY is required for a real OpenAI-compatible client")
        self._opener = opener or urlopen
        self._sleep = sleep
        self._random = random_value

    def _body(self, prompt: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
        }
        if self.config.response_format == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "extraction_envelope", "strict": True, "schema": provider_schema()},
            }
        elif self.config.response_format == "json_object":
            body["response_format"] = {"type": "json_object"}
        return body

    @staticmethod
    def _content(choice: Any) -> str:
        if not isinstance(choice, dict):
            raise ProviderEmptyResponseError("OpenAI-compatible response has no valid choice")
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text = "".join(part.get("text", "") for part in content if isinstance(part, dict) and isinstance(part.get("text"), str))
            if text:
                return text
        raise ProviderEmptyResponseError("OpenAI-compatible response has empty message content")

    def _request(self, prompt: str) -> str:
        request = Request(
            chat_completions_url(self.config.base_url),
            data=json.dumps(self._body(prompt)).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        response = None
        try:
            response = self._opener(request, timeout=self.config.timeout_seconds)
            raw = response.read()
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw
        except HTTPError as exc:
            status = exc.code
            if status == 401:
                raise ProviderAuthenticationError("OpenAI-compatible authentication failed") from exc
            if status == 403:
                raise ProviderPermissionError("OpenAI-compatible permission denied") from exc
            raise ProviderRequestError(f"OpenAI-compatible request failed with HTTP {status}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise TimeoutError from exc
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise TimeoutError from exc
            raise ProviderRequestError("OpenAI-compatible request failed") from exc
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def extract(self, prompt: str) -> Any:
        if len(prompt) > self.config.max_input_chars:
            raise ProviderRequestError("OpenAI-compatible input exceeds configured limit")
        last: Exception | None = None
        for attempt in range(self.config.retries + 1):
            try:
                raw = self._request(prompt)
                try:
                    response = json.loads(raw)
                    choices = response.get("choices") if isinstance(response, dict) else None
                    if not choices:
                        raise ProviderEmptyResponseError("OpenAI-compatible response has no choices")
                    content = self._content(choices[0]).strip()
                    if content.startswith("```"):
                        lines = content.splitlines()
                        if len(lines) >= 2 and lines[-1].strip() == "```":
                            content = "\n".join(lines[1:-1]).strip()
                    if not content:
                        raise ProviderEmptyResponseError("OpenAI-compatible response has empty content")
                    return parse_envelope(json.loads(content))
                except (ProviderEmptyResponseError, ProviderSchemaError):
                    raise
                except Exception as exc:
                    raise ProviderSchemaError("OpenAI-compatible response did not match the extraction schema") from exc
            except (ProviderAuthenticationError, ProviderPermissionError, ProviderSchemaError, ProviderEmptyResponseError):
                raise
            except TimeoutError as exc:
                last = exc
            except ProviderRequestError as exc:
                last = exc
                status = getattr(exc.__cause__, "code", None)
                if status not in (429,) and not (isinstance(status, int) and status >= 500):
                    raise
            if attempt >= self.config.retries:
                raise ProviderRequestError("OpenAI-compatible request failed") from last
            self._sleep(min(8.0, 0.5 * (2 ** attempt)) + self._random() * 0.25)
        raise ProviderRequestError("OpenAI-compatible request failed") from last
