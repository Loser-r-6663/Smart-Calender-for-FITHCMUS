"""Parser and lightweight text-analysis extension points."""

from dataclasses import dataclass
from typing import Protocol, Sequence

from .models import RawCrawlerInput, TaskCandidate


class Parser(Protocol):
    """Turn one opaque crawler envelope into zero or more candidates."""

    def parse(self, raw: RawCrawlerInput) -> Sequence[TaskCandidate]: ...


@dataclass(frozen=True, slots=True)
class TextFeatures:
    """Small internal text features for normalization or duplicate filtering."""

    original: str
    normalized: str
    tokens: tuple[str, ...] = ()


class NaturalLanguageAnalyzer(Protocol):
    """Optional lightweight analysis; not a search or LLM interface."""

    def analyze(self, text: str) -> TextFeatures: ...
