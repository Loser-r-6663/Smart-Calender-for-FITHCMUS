"""Boundaries and value objects owned by the backend data processor.

This package does not own crawlers, persisted Tasks, databases, scheduling, or
other task-layer responsibilities.
"""

from .deduplication import DedupAction, DeduplicationResult, DuplicateChecker
from .models import (
    DRLCategory,
    RawCrawlerInput,
    SourcePlatform,
    TaskCandidate,
    TaskStatus,
    TaskType,
)
from .parser import NaturalLanguageAnalyzer, Parser, TextFeatures
from .time import GMT_PLUS_7, normalize_datetime
from .validation import (
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    Validator,
)

__all__ = [
    "DedupAction",
    "DeduplicationResult",
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
    "ValidationIssue",
    "ValidationResult",
    "ValidationSeverity",
    "Validator",
    "normalize_datetime",
]
