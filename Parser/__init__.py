"""Boundaries and value objects owned by the backend data processor.

This package does not own crawlers, persisted Tasks, databases, scheduling, or
other task-layer responsibilities.
"""

from .deduplication import DedupAction, DeduplicationResult, DuplicateChecker
from .crawler_adapter import CrawlerAdapterError, adapt_crawl_results
from .models import (
    DRLCategory,
    RawCrawlerInput,
    SourcePlatform,
    TaskCandidate,
    TaskStatus,
    TaskType,
)
from .parser import NaturalLanguageAnalyzer, Parser, TextFeatures
from .config import OpenAICompatibleConfig
from .factory import create_llm_gateway
from .llm_gateway import LLMGateway
from .openai_compatible_client import OpenAICompatibleClient
from .raw_deduplication import (
    InMemoryRawFingerprintStore,
    RawDedupAction,
    RawDedupReason,
    RawDeduplicationError,
    RawDeduplicationResult,
    RawDuplicateChecker,
    RawFingerprint,
    RawFingerprintStore,
    canonicalize_url,
    fingerprint_raw_input,
)
from .time import GMT_PLUS_7, normalize_datetime

__all__ = [
    "DedupAction",
    "DeduplicationResult",
    "CrawlerAdapterError",
    "DRLCategory",
    "DuplicateChecker",
    "GMT_PLUS_7",
    "NaturalLanguageAnalyzer",
    "Parser",
    "RawCrawlerInput",
    "SourcePlatform",
    "TaskCandidate",
    "TaskStatus",
    "TaskType",
    "TextFeatures",
    "normalize_datetime",
    "adapt_crawl_results",
    "InMemoryRawFingerprintStore",
    "RawDedupAction",
    "RawDedupReason",
    "RawDeduplicationError",
    "RawDeduplicationResult",
    "RawDuplicateChecker",
    "RawFingerprint",
    "RawFingerprintStore",
    "canonicalize_url",
    "fingerprint_raw_input",
    "LLMGateway",
    "OpenAICompatibleConfig",
    "OpenAICompatibleClient",
    "create_llm_gateway",
]
