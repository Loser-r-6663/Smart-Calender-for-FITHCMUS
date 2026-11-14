"""Stable public API for parsing, deduplication, and REST persistence."""

# Re-export the supported surface so callers need not depend on module layout.
from .adapters import CrawlerAdapterError, adapt_crawl_results
from .api_client import DatabaseApiClient
from .deduplication import (
    CandidateDeduplicationError,
    TEXT_SIMILARITY_THRESHOLD,
    deduplicate_task_candidates,
)
from .errors import (
    DatabaseApiConflictError,
    DatabaseApiAuthenticationError,
    DatabaseApiPermissionError,
    DatabaseApiError,
    DatabaseApiUnavailableError,
    DatabaseApiValidationError,
    ParserError,
    ProviderError,
)
from .extraction import GMT_PLUS_7, UNKNOWN_DEADLINE, LLMExtractor, LLMParser, normalize_datetime
from .manager import (
    ParserManager,
    PipelineBatchResult,
    PipelineItemResult,
    PipelineStage,
    StageError,
    StageResult,
    StageStatus,
)
from .models import (
    DRLCategory,
    RawCrawlerInput,
    SourcePlatform,
    TaskCandidate,
    TaskStatus,
    TaskType,
)
from .providers import (
    ExtractionEnvelope,
    ExtractedTask,
    GeminiClient,
    GeminiConfig,
    LLMGateway,
    OpenAICompatibleClient,
    OpenAICompatibleConfig,
    create_llm_gateway,
    parse_envelope,
    provider_schema,
)


__all__ = [
    "CrawlerAdapterError",
    "CandidateDeduplicationError",
    "DatabaseApiClient",
    "DatabaseApiConflictError",
    "DatabaseApiAuthenticationError",
    "DatabaseApiPermissionError",
    "DatabaseApiError",
    "DatabaseApiUnavailableError",
    "DatabaseApiValidationError",
    "DRLCategory",
    "ExtractionEnvelope",
    "ExtractedTask",
    "GeminiClient",
    "GeminiConfig",
    "GMT_PLUS_7",
    "UNKNOWN_DEADLINE",
    "TEXT_SIMILARITY_THRESHOLD",
    "LLMExtractor",
    "LLMGateway",
    "LLMParser",
    "OpenAICompatibleClient",
    "OpenAICompatibleConfig",
    "ParserError",
    "ParserManager",
    "PipelineBatchResult",
    "PipelineItemResult",
    "PipelineStage",
    "RawCrawlerInput",
    "SourcePlatform",
    "StageError",
    "StageResult",
    "StageStatus",
    "TaskCandidate",
    "TaskStatus",
    "TaskType",
    "adapt_crawl_results",
    "deduplicate_task_candidates",
    "create_llm_gateway",
    "normalize_datetime",
    "parse_envelope",
    "provider_schema",
]
