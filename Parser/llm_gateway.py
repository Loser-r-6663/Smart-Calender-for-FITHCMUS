"""Provider-neutral interface for structured language-model extraction."""

from typing import Any, Protocol


class LLMGateway(Protocol):
    def extract(self, prompt: str) -> Any: ...
