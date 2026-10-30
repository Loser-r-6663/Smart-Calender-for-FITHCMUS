"""Environment-backed Gemini configuration."""

from dataclasses import dataclass, field
import os

from .errors import ConfigurationError


DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"


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
