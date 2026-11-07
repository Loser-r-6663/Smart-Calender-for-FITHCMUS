"""Provider schemas, configuration, and generic structured LLM clients."""

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import random
import re
import socket
import time
from typing import Any, Callable, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import (
    ConfigurationError,
    ProviderAuthenticationError,
    ProviderEmptyResponseError,
    ProviderError,
    ProviderPermissionError,
    ProviderRequestError,
    ProviderSchemaError,
)


TaskTypeValue = Literal[
    "class", "assignment", "exam", "event", "personal", "tuition"
]
DRLCategoryValue = Literal[
    "dieu_1", "dieu_2", "dieu_3", "dieu_4", "dieu_5"
]
_TIME_ONLY = re.compile(r"^\d{2}:\d{2}(?::\d{2})?$")


def _clear_class_time_only(value: Any) -> Any:
    if not isinstance(value, dict) or value.get("type") != "class":
        return value

    data = value.copy()
    time_values = [
        data[field]
        for field in ("start_time", "end_time")
        if isinstance(data.get(field), str) and _TIME_ONLY.fullmatch(data[field])
    ]
    if not time_values:
        return data

    start = data.get("start_time")
    end = data.get("end_time")
    time_range = f"{start}-{end}" if isinstance(start, str) and isinstance(end, str) else time_values[0]
    recurrence = data.get("recurrence")
    if not recurrence:
        data["recurrence"] = time_range
    elif isinstance(recurrence, str):
        normalized_recurrence = re.sub(r"\s*-\s*", "-", recurrence)
        if time_range not in normalized_recurrence:
            data["recurrence"] = f"{recurrence}; {time_range}"

    for field in ("start_time", "end_time"):
        if isinstance(data.get(field), str) and _TIME_ONLY.fullmatch(data[field]):
            data[field] = None
    return data


class ExtractedTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    type: TaskTypeValue | None = None
    course_code: str | None = None
    description: str | None = None
    target_audience: str | None = None
    location: str | None = None
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    deadline: datetime | None = None
    estimated_hours: float | None = None
    training_points: int | None = None
    drl_category: DRLCategoryValue | None = None
    recurrence: str | None = None

    @model_validator(mode="before")
    @classmethod
    def clear_class_time_only_datetimes(cls, value: Any) -> Any:
        return _clear_class_time_only(value)


class ExtractionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks: list[ExtractedTask] = Field(default_factory=list)


def provider_schema() -> dict[str, Any]:
    """Return the strict schema with provider-incompatible extras removed."""

    def sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: sanitize(item)
                for key, item in value.items()
                if key != "additionalProperties"
            }
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        return value

    return sanitize(ExtractionEnvelope.model_json_schema())


def parse_envelope(value: Any) -> ExtractionEnvelope:
    if isinstance(value, ExtractionEnvelope):
        return value
    return ExtractionEnvelope.model_validate(value)


class LLMGateway(Protocol):
    def extract(self, prompt: str) -> Any: ...


DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def _env_number(
    name: str,
    default: str,
    converter: Callable[[str], Any],
) -> Any:
    try:
        return converter(os.getenv(name, default))
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{name} must be a valid number") from exc


@dataclass(frozen=True, slots=True)
class GeminiConfig:
    api_key: str = field(default="", repr=False)
    model: str = DEFAULT_GEMINI_MODEL
    max_input_chars: int = 30000
    max_output_tokens: int = 4096
    timeout_seconds: float = 30.0
    retries: int = 2
    temperature: float = 0.0

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ConfigurationError("Gemini model must be non-empty")
        if self.max_input_chars <= 0 or self.max_output_tokens <= 0:
            raise ConfigurationError("Gemini limits must be positive")
        if self.timeout_seconds <= 0 or self.retries < 0:
            raise ConfigurationError("Gemini timeout and retries are invalid")
        if not 0 <= self.temperature <= 2:
            raise ConfigurationError("Gemini temperature must be between 0 and 2")

    @classmethod
    def from_env(cls, require_key: bool = True) -> "GeminiConfig":
        key = os.getenv("GEMINI_API_KEY", "")
        if require_key and not key:
            raise ConfigurationError("GEMINI_API_KEY is required")
        return cls(
            api_key=key,
            model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        )


@dataclass(frozen=True, slots=True)
class OpenAICompatibleConfig:
    api_key: str = field(default="", repr=False)
    base_url: str = DEFAULT_OPENAI_BASE_URL
    model: str = DEFAULT_OPENAI_MODEL
    max_input_chars: int = 30000
    max_output_tokens: int = 4096
    timeout_seconds: float = 30.0
    retries: int = 2
    temperature: float = 0.0
    response_format: str = "json_object"

    def __post_init__(self) -> None:
        if not self.base_url.strip() or not self.model.strip():
            raise ConfigurationError("OpenAI-compatible URL and model are required")
        if self.response_format not in {"json_schema", "json_object", "none"}:
            raise ConfigurationError("OPENAI_RESPONSE_FORMAT is invalid")
        if self.max_input_chars <= 0 or self.max_output_tokens <= 0:
            raise ConfigurationError("OpenAI-compatible limits must be positive")
        if self.timeout_seconds <= 0 or self.retries < 0:
            raise ConfigurationError("OpenAI-compatible timeout and retries are invalid")
        if not 0 <= self.temperature <= 2:
            raise ConfigurationError(
                "OpenAI-compatible temperature must be between 0 and 2"
            )

    @classmethod
    def from_env(cls, require_key: bool = True) -> "OpenAICompatibleConfig":
        key = os.getenv("OPENAI_API_KEY", "")
        if require_key and not key:
            raise ConfigurationError("OPENAI_API_KEY is required")
        return cls(
            api_key=key,
            base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
            model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            max_input_chars=_env_number("OPENAI_MAX_INPUT_CHARS", "30000", int),
            max_output_tokens=_env_number("OPENAI_MAX_OUTPUT_TOKENS", "4096", int),
            timeout_seconds=_env_number("OPENAI_TIMEOUT_SECONDS", "30.0", float),
            retries=_env_number("OPENAI_RETRIES", "2", int),
            temperature=_env_number("OPENAI_TEMPERATURE", "0.0", float),
            response_format=os.getenv("OPENAI_RESPONSE_FORMAT", "json_object"),
        )


class GeminiClient:
    """Lazy adapter around the optional google-genai SDK."""

    def __init__(self, config: GeminiConfig | None = None, sdk_client: Any = None) -> None:
        self.config = config or GeminiConfig.from_env()
        injected = sdk_client is not None
        if sdk_client is None:
            try:
                from google import genai

                sdk_client = genai.Client(
                    api_key=self.config.api_key,
                    http_options={"timeout": int(self.config.timeout_seconds * 1000)},
                )
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
                        "response_schema": provider_schema(),
                    },
                )
                parsed = getattr(response, "parsed", None)
                if parsed is not None:
                    try:
                        return parse_envelope(parsed)
                    except Exception as exc:
                        raise ProviderSchemaError(
                            "Gemini response did not match the extraction schema"
                        ) from exc
                text = getattr(response, "text", None)
                if not text:
                    raise ProviderEmptyResponseError("Gemini returned an empty response")
                try:
                    return parse_envelope(json.loads(text))
                except Exception as exc:
                    raise ProviderSchemaError(
                        "Gemini response did not match the extraction schema"
                    ) from exc
            except ProviderError:
                raise
            except Exception as exc:
                last = exc
                status = getattr(exc, "status_code", getattr(exc, "code", None))
                if status == 401:
                    raise ProviderAuthenticationError("Gemini authentication failed") from exc
                if status == 403:
                    raise ProviderPermissionError("Gemini permission denied") from exc
                transient = (
                    status == 429
                    or isinstance(status, int) and status >= 500
                    or isinstance(exc, TimeoutError)
                )
                if not transient or attempt >= self.config.retries:
                    raise ProviderRequestError("Gemini request failed") from exc
                time.sleep(min(8.0, 0.5 * 2**attempt) + random.random() * 0.25)
        raise ProviderRequestError("Gemini request failed") from last


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
            raise ProviderRequestError(
                "OPENAI_API_KEY is required for a real OpenAI-compatible client"
            )
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
                "json_schema": {
                    "name": "extraction_envelope",
                    "strict": True,
                    "schema": provider_schema(),
                },
            }
        elif self.config.response_format == "json_object":
            body["response_format"] = {"type": "json_object"}
        return body

    @staticmethod
    def _content(choice: Any) -> str:
        if not isinstance(choice, dict):
            raise ProviderEmptyResponseError(
                "OpenAI-compatible response has no valid choice"
            )
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            text = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
            if text:
                return text
        finish_reason = choice.get("finish_reason")
        safe_finish_reason = (
            repr(finish_reason[:64])
            if isinstance(finish_reason, str)
            else "unknown"
        )
        alternate_fields = [
            name
            for name in ("reasoning_content", "reasoning", "analysis")
            if isinstance(message, dict) and message.get(name)
        ]
        alternatives = ", ".join(alternate_fields) or "none"
        raise ProviderEmptyResponseError(
            "OpenAI-compatible response has empty message content "
            f"(finish_reason={safe_finish_reason}, alternate_fields={alternatives})"
        )

    def _request(self, prompt: str) -> str:
        request = Request(
            chat_completions_url(self.config.base_url),
            data=json.dumps(self._body(prompt)).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        response = None
        try:
            response = self._opener(request, timeout=self.config.timeout_seconds)
            raw = response.read()
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw
        except HTTPError as exc:
            if exc.code == 401:
                raise ProviderAuthenticationError(
                    "OpenAI-compatible authentication failed"
                ) from exc
            if exc.code == 403:
                raise ProviderPermissionError(
                    "OpenAI-compatible permission denied"
                ) from exc
            raise ProviderRequestError(
                f"OpenAI-compatible request failed with HTTP {exc.code}"
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise TimeoutError from exc
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise TimeoutError from exc
            raise ProviderRequestError(
                "OpenAI-compatible request failed"
            ) from exc
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def extract(self, prompt: str) -> Any:
        if len(prompt) > self.config.max_input_chars:
            raise ProviderRequestError(
                "OpenAI-compatible input exceeds configured limit"
            )
        last: Exception | None = None
        for attempt in range(self.config.retries + 1):
            try:
                response = json.loads(self._request(prompt))
                choices = response.get("choices") if isinstance(response, dict) else None
                if not choices:
                    raise ProviderEmptyResponseError(
                        "OpenAI-compatible response has no choices"
                    )
                content = self._content(choices[0]).strip()
                if content.startswith("```"):
                    lines = content.splitlines()
                    if len(lines) >= 2 and lines[-1].strip() == "```":
                        content = "\n".join(lines[1:-1]).strip()
                if not content:
                    raise ProviderEmptyResponseError(
                        "OpenAI-compatible response has empty content"
                    )
                return parse_envelope(json.loads(content))
            except (
                ProviderAuthenticationError,
                ProviderPermissionError,
                ProviderSchemaError,
                ProviderEmptyResponseError,
            ):
                raise
            except (TimeoutError, ProviderRequestError) as exc:
                last = exc
                status = getattr(exc.__cause__, "code", None)
                retryable = status == 429 or isinstance(status, int) and status >= 500
                if isinstance(exc, ProviderRequestError) and not retryable:
                    raise
            except Exception as exc:
                raise ProviderSchemaError(
                    "OpenAI-compatible response did not match the extraction schema"
                ) from exc
            if attempt >= self.config.retries:
                raise ProviderRequestError(
                    "OpenAI-compatible request failed"
                ) from last
            self._sleep(min(8.0, 0.5 * 2**attempt) + self._random() * 0.25)
        raise ProviderRequestError("OpenAI-compatible request failed") from last


def create_llm_gateway(provider: str | None = None) -> LLMGateway:
    selected = (provider or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
    if selected == "gemini":
        return GeminiClient()
    if selected in {"openai_compatible", "openai-compatible", "openai", "chatgpt"}:
        return OpenAICompatibleClient(OpenAICompatibleConfig.from_env())
    raise ConfigurationError(f"unsupported LLM_PROVIDER: {selected}")
