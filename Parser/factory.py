"""Lazy provider selection."""

import os

from .config import OpenAICompatibleConfig
from .errors import ConfigurationError
from .llm_gateway import LLMGateway


def create_llm_gateway(provider: str | None = None) -> LLMGateway:
    selected = (provider or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
    if selected in {"gemini"}:
        from .gemini_client import GeminiClient
        return GeminiClient()
    if selected in {"openai_compatible", "openai-compatible", "openai", "chatgpt"}:
        from .openai_compatible_client import OpenAICompatibleClient
        return OpenAICompatibleClient(OpenAICompatibleConfig.from_env())
    raise ConfigurationError(f"unsupported LLM_PROVIDER: {selected}")
