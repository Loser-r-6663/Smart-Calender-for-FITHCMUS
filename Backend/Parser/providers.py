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

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

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
    # Class time-only values lack a date, so preserve them as recurrence text instead.
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
    # Pydantic supplies shared validation for every provider response.
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    type: TaskTypeValue | None = None
    course: str | None = None
    description: str | None = None
    target_audience: str | None = None
    location: str | None = None
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    deadline: datetime | None = None
    estimated_hours: float | None = None
    training_points: int | None = Field(default=None, ge=0, le=25) # Capped max training point to 25, which is the same as the official mapping according to STSV
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
        # Some providers reject this JSON Schema keyword even though Pydantic emits it.
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
    # Structured validation keeps provider-specific response handling at one boundary.
    if isinstance(value, ExtractionEnvelope):
        return value
    return ExtractionEnvelope.model_validate(value)


def _safe_schema_diagnostic(exc: Exception, output_chars: int | None = None) -> str:
    if isinstance(exc, json.JSONDecodeError):
        return (
            f"category=json message={str(exc)[:120]} line={exc.lineno} "
            f"column={exc.colno} position={exc.pos} output_chars={output_chars or 0}"
        )
    if isinstance(exc, ValidationError):
        details = []
        for error in exc.errors(include_input=False)[:5]:
            path = ".".join(str(part) for part in error.get("loc", ())) or "root"
            details.append(
                f"{path}:{error.get('type', 'invalid')}:{str(error.get('msg', 'invalid'))[:100]}"
            )
        return "category=pydantic " + "; ".join(details)
    return f"category=validation type={type(exc).__name__}"


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
    max_output_tokens: int = 8192
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
    max_output_tokens: int = 8192
    timeout_seconds: float = 30.0
    retries: int = 2
    temperature: float = 0.0
    response_format: str = "json_object"
    output_retries: int = 1
    length_retry_tokens: int = 8192

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
        if self.output_retries < 0 or self.length_retry_tokens <= 0:
            raise ConfigurationError("OpenAI-compatible output retry settings are invalid")

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
            max_output_tokens=_env_number("OPENAI_MAX_OUTPUT_TOKENS", "8192", int),
            timeout_seconds=_env_number("OPENAI_TIMEOUT_SECONDS", "30.0", float),
            retries=_env_number("OPENAI_RETRIES", "2", int),
            temperature=_env_number("OPENAI_TEMPERATURE", "0.0", float),
            response_format=os.getenv("OPENAI_RESPONSE_FORMAT", "json_object"),
            output_retries=_env_number("OPENAI_OUTPUT_RETRIES", "1", int),
            length_retry_tokens=_env_number("OPENAI_LENGTH_RETRY_TOKENS", "8192", int),
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
                    except (ValidationError, json.JSONDecodeError) as exc:
                        raise ProviderSchemaError(_safe_schema_diagnostic(exc)) from exc
                text = getattr(response, "text", None)
                if not text:
                    raise ProviderEmptyResponseError("Gemini returned an empty response")
                try:
                    return parse_envelope(json.loads(text))
                except (ValidationError, json.JSONDecodeError) as exc:
                    raise ProviderSchemaError(
                        _safe_schema_diagnostic(exc, len(text))
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
                # Exponential backoff with jitter avoids synchronized retry bursts.
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

    def _body(self, prompt: str, max_tokens: int | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "max_tokens": max_tokens or self.config.max_output_tokens,
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

    def _request_once(self, prompt: str, max_tokens: int | None = None) -> str:
        request = Request(
            chat_completions_url(self.config.base_url),
            data=json.dumps(self._body(prompt, max_tokens)).encode("utf-8"),
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
            # Translate transport-specific failures into the provider error contract.
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
        except (ConnectionError, OSError, TimeoutError, socket.timeout) as exc:
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

    def _request(self, prompt: str, max_tokens: int | None = None) -> str:
        """Execute transport retries without consuming an output retry."""
        for attempt in range(self.config.retries + 1):
            try:
                return self._request_once(prompt, max_tokens)
            except (ProviderAuthenticationError, ProviderPermissionError):
                raise
            except (TimeoutError, ProviderRequestError) as exc:
                cause = exc.__cause__
                status = getattr(cause, "code", None)
                retryable = (
                    isinstance(exc, TimeoutError)
                    or isinstance(cause, URLError) and not isinstance(cause, HTTPError)
                    or status == 429
                    or isinstance(status, int) and status >= 500
                )
                if not retryable or attempt >= self.config.retries:
                    raise
                self._sleep(min(8.0, 0.5 * 2**attempt) + self._random() * 0.25)

    @staticmethod
    def _validation_message(exc: ValidationError) -> str:
        details = []
        for error in exc.errors(include_input=False)[:5]:
            path = ".".join(str(part) for part in error.get("loc", ())) or "root"
            details.append(
                f"{path}:{error.get('type', 'invalid')}:"
                f"{str(error.get('msg', 'invalid'))[:100]}"
            )
        return "category=pydantic " + "; ".join(details)

    def extract(self, prompt: str) -> Any:
        if len(prompt) > self.config.max_input_chars:
            raise ProviderRequestError(
                "OpenAI-compatible input exceeds configured limit"
            )
        output_prompt = prompt
        last: Exception | None = None
        retry_tokens: int | None = None
        for output_attempt in range(self.config.output_retries + 1):
            try:
                raw_response = self._request(output_prompt, retry_tokens)
                try:
                    response = json.loads(raw_response)
                except json.JSONDecodeError as exc:
                    raise ProviderSchemaError(
                        "category=json "
                        f"message={str(exc)[:120]} line={exc.lineno} "
                        f"column={exc.colno} position={exc.pos} "
                        f"finish_reason=unknown output_chars={len(raw_response)}"
                    ) from exc
                choices = response.get("choices") if isinstance(response, dict) else None
                if not isinstance(choices, list) or not choices:
                    raise ProviderEmptyResponseError(
                        "OpenAI-compatible response has no choices array"
                    )
                choice = choices[0]
                if not isinstance(choice, dict):
                    raise ProviderSchemaError(
                        "OpenAI-compatible response has an invalid first choice"
                    )
                if choice.get("finish_reason") == "length":
                    raise ProviderSchemaError("category=length finish_reason=length")
                content = self._content(choice).strip()
                try:
                    return parse_envelope(json.loads(content))
                except json.JSONDecodeError as exc:
                    raise ProviderSchemaError(
                        "category=json "
                        f"message={str(exc)[:120]} line={exc.lineno} "
                        f"column={exc.colno} position={exc.pos} "
                        f"finish_reason={choice.get('finish_reason', 'unknown')} "
                        f"output_chars={len(content)}"
                    ) from exc
                except ValidationError as exc:
                    raise ProviderSchemaError(self._validation_message(exc)) from exc
            except (ProviderSchemaError, ProviderEmptyResponseError) as exc:
                last = exc
                if "finish_reason=length" in str(exc):
                    retry_tokens = self.config.length_retry_tokens
            if output_attempt >= self.config.output_retries:
                raise last or ProviderSchemaError("OpenAI-compatible output failed")
            output_prompt = prompt + "\nReturn only valid JSON matching the requested shape, without analysis."
        raise ProviderSchemaError("OpenAI-compatible output failed")


def create_llm_gateway(provider: str | None = None) -> LLMGateway:
    selected = (provider or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
    if selected == "gemini":
        return GeminiClient()
    if selected in {"openai_compatible", "openai-compatible", "openai", "chatgpt"}:
        return OpenAICompatibleClient(OpenAICompatibleConfig.from_env())
    raise ConfigurationError(f"unsupported LLM_PROVIDER: {selected}")
