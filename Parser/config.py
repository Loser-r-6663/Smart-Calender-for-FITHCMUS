"""Immutable environment-backed provider configuration."""

from dataclasses import dataclass, field
import os

from .errors import ConfigurationError


DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


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
        if not isinstance(self.model, str) or not self.model.strip():
            raise ConfigurationError("Gemini model must be non-empty")
        if (not isinstance(self.max_input_chars, int) or self.max_input_chars <= 0
                or not isinstance(self.max_output_tokens, int) or self.max_output_tokens <= 0
                or not isinstance(self.timeout_seconds, (int, float)) or self.timeout_seconds <= 0):
            raise ConfigurationError("Gemini limits and timeout must be positive")
        if not isinstance(self.retries, int) or self.retries < 0:
            raise ConfigurationError("Gemini retries cannot be negative")
        if not isinstance(self.temperature, (int, float)) or not 0 <= self.temperature <= 2:
            raise ConfigurationError("Gemini temperature must be between 0 and 2")

    @classmethod
    def from_env(cls, require_key: bool = True) -> "GeminiConfig":
        key = os.getenv("GEMINI_API_KEY", "")
        if require_key and not key:
            raise ConfigurationError("GEMINI_API_KEY is required")
        return cls(api_key=key, model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL))


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
        if not isinstance(self.base_url, str) or not self.base_url.strip():
            raise ConfigurationError("OpenAI-compatible base URL and model must be non-empty")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ConfigurationError("OpenAI-compatible base URL and model must be non-empty")
        if not isinstance(self.response_format, str) or self.response_format not in {"json_schema", "json_object", "none"}:
            raise ConfigurationError("OPENAI_RESPONSE_FORMAT must be json_schema, json_object, or none")
        if (type(self.max_input_chars) is not int or self.max_input_chars <= 0
                or type(self.max_output_tokens) is not int or self.max_output_tokens <= 0
                or isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float))
                or self.timeout_seconds <= 0):
            raise ConfigurationError("OpenAI-compatible limits and timeout must be positive")
        if type(self.retries) is not int or self.retries < 0:
            raise ConfigurationError("OpenAI-compatible retries cannot be negative")
        if isinstance(self.temperature, bool) or not isinstance(self.temperature, (int, float)) or not 0 <= self.temperature <= 2:
            raise ConfigurationError("OpenAI-compatible temperature must be between 0 and 2")

    @classmethod
    def from_env(cls, require_key: bool = True) -> "OpenAICompatibleConfig":
        key = os.getenv("OPENAI_API_KEY", "")
        if require_key and not key:
            raise ConfigurationError("OPENAI_API_KEY is required")
        return cls(api_key=key, base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
                   model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
                   response_format=os.getenv("OPENAI_RESPONSE_FORMAT", "json_object"))
