"""Traceable orchestration of extraction, deduplication, and REST persistence."""

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from datetime import datetime
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from .adapters import adapt_crawl_results
from .api_client import DatabaseApiClient
from .deduplication import deduplicate_task_candidates
from .extraction import LLMExtractor, UNKNOWN_DEADLINE
from .models import RawCrawlerInput, TaskCandidate
from .providers import create_llm_gateway


class StageStatus(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


class PipelineStage(str, Enum):
    ADAPT = "adapt"
    PARSE = "parse"
    CANDIDATE_DEDUP = "candidate_dedup"
    PREPARE = "prepare"
    API_HEALTH = "api_health"
    SEND = "send"


@dataclass(frozen=True, slots=True)
class StageError:
    """Safe, compact description of a failed stage."""

    type: str
    message: str

    def __post_init__(self) -> None:
        message = " ".join(self.message.split())[:500]
        object.__setattr__(self, "message", message)


@dataclass(frozen=True, slots=True)
class StageResult:
    input: Any
    output: Any
    status: StageStatus
    error: StageError | None
    elapsed_ms: float
    stage: PipelineStage | None = None


@dataclass(frozen=True, slots=True)
class PipelineItemResult:
    raw: RawCrawlerInput
    stages: tuple[StageResult, ...]
    candidates: tuple[TaskCandidate, ...] = ()
    persisted: tuple[dict[str, Any], ...] = ()
    status: StageStatus = StageStatus.SUCCESS
    error: StageError | None = None


@dataclass(frozen=True, slots=True)
class PipelineBatchResult:
    items: tuple[PipelineItemResult, ...]
    adapted: tuple[RawCrawlerInput, ...] = ()
    status: StageStatus = StageStatus.SUCCESS
    error: StageError | None = None

    @property
    def processed(self) -> int:
        return sum(item.status is StageStatus.SUCCESS for item in self.items)

    @property
    def persisted(self) -> int:
        return sum(len(item.persisted) for item in self.items)

    @property
    def failed(self) -> int:
        return sum(item.status is StageStatus.FAILED for item in self.items)

    @property
    def skipped(self) -> int:
        return sum(item.status is StageStatus.SKIPPED for item in self.items)


class ParserManager:
    def __init__(
        self,
        extractor: Any,
        database_api: DatabaseApiClient | None = None,
        stop_on_error: bool = False,
        id_factory: Callable[[TaskCandidate], str] | None = None,
    ) -> None:
        self.extractor = extractor
        self.database_api = database_api
        self.stop_on_error = stop_on_error
        self.id_factory = id_factory or self._default_id

    @staticmethod
    def _default_id(candidate: TaskCandidate) -> str:
        """Create a stable ID from persisted candidate data, before preparation."""

        def serialize(value: Any) -> Any:
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, tuple):
                return [serialize(item) for item in value]
            if isinstance(value, dict):
                return {key: serialize(item) for key, item in sorted(value.items())}
            return value

        identity = {
            field: serialize(getattr(candidate, field))
            for field in candidate.__dataclass_fields__
            if field not in {"id", "embedding", "updated_at"}
        }
        canonical = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "task-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

    @classmethod
    def from_env(cls, **kwargs: Any) -> "ParserManager":
        database_api = DatabaseApiClient()
        extractor = LLMExtractor(create_llm_gateway())
        return cls(extractor, database_api, **kwargs)

    @staticmethod
    def _stage(
        stage: PipelineStage,
        value: Any,
        operation: Callable[[], Any],
    ) -> StageResult:
        # Every operation is timed and captured so failures remain traceable by stage.
        started = time.perf_counter()
        try:
            output = operation()
        except Exception as exc:
            return StageResult(
                input=value,
                output=None,
                status=StageStatus.FAILED,
                error=StageError(type(exc).__name__, str(exc)),
                elapsed_ms=(time.perf_counter() - started) * 1000,
                stage=stage,
            )
        return StageResult(
            input=value,
            output=output,
            status=StageStatus.SUCCESS,
            error=None,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            stage=stage,
        )

    def adapt_crawler_results(
        self,
        results: Any,
        captured_at: datetime | None = None,
    ) -> StageResult:
        return self._stage(
            PipelineStage.ADAPT,
            results,
            lambda: adapt_crawl_results(results, captured_at=captured_at),
        )

    def parse(self, raw: RawCrawlerInput) -> StageResult:
        return self._stage(
            PipelineStage.PARSE,
            raw,
            lambda: tuple(self.extractor.parse(raw)),
        )

    def deduplicate_candidates(
        self,
        candidates: tuple[TaskCandidate, ...],
        retained_candidates: Sequence[TaskCandidate] = (),
    ) -> StageResult:
        return self._stage(
            PipelineStage.CANDIDATE_DEDUP,
            candidates,
            lambda: deduplicate_task_candidates(candidates, retained_candidates),
        )

    def prepare_task(self, candidate: TaskCandidate) -> StageResult:
        stage_input = {"candidate": candidate}

        def prepare() -> dict[str, Any]:
            fields = (
                "title", "type", "course", "description", "target_audience",
                "location", "registration_start", "registration_end", "start_time",
                "end_time", "deadline", "estimated_hours", "training_points",
                "drl_category", "recurrence", "status", "is_manual", "source_url",
                "source_platform", "updated_at",
            )
            data = {field: getattr(candidate, field) for field in fields}
            # Generate the identity before adding the scheduler-only sentinel.
            data["id"] = self.id_factory(candidate)
            if (
                candidate.type.value in {"assignment", "tuition"}
                and candidate.deadline is None
            ):
                # Temporary cross-component sentinel; the scheduler must treat this as unknown.
                data["deadline"] = UNKNOWN_DEADLINE
            # Convert domain enums and datetimes at the API serialization boundary.
            return {
                key: (
                    value.value
                    if isinstance(value, Enum)
                    else value.isoformat()
                    if isinstance(value, datetime)
                    else value
                )
                for key, value in data.items()
                if value is not None
            }

        return self._stage(PipelineStage.PREPARE, stage_input, prepare)

    def check_api_health(self) -> StageResult:
        def check() -> Any:
            if self.database_api is None:
                raise RuntimeError("database API client is not configured")
            return self.database_api.check_health()

        return self._stage(PipelineStage.API_HEALTH, None, check)

    def send_to_database(self, payload: dict[str, Any]) -> StageResult:
        def send() -> Any:
            if self.database_api is None:
                raise RuntimeError("database API client is not configured")
            # Conflict recovery is intentionally disabled until read permission/idempotency is settled.
            return self.database_api.create_task(payload)

        return self._stage(PipelineStage.SEND, payload, send)

    def process_raw(
        self,
        raw: RawCrawlerInput,
        api_already_checked: bool = False,
        retained_candidates: list[TaskCandidate] | None = None,
    ) -> PipelineItemResult:
        stages: list[StageResult] = []
        if not api_already_checked:
            # Fail before extraction to avoid paying LLM cost while persistence is down.
            health = self.check_api_health()
            stages.append(health)
            if health.status is StageStatus.FAILED:
                return PipelineItemResult(
                    raw=raw,
                    stages=tuple(stages),
                    status=StageStatus.FAILED,
                    error=health.error,
                )
        parsed = self.parse(raw)
        stages.append(parsed)
        if parsed.status is StageStatus.FAILED:
            return PipelineItemResult(
                raw=raw,
                stages=tuple(stages),
                status=StageStatus.FAILED,
                error=parsed.error,
            )
        candidate_dedup = self.deduplicate_candidates(
            parsed.output,
            retained_candidates if retained_candidates is not None else (),
        )
        stages.append(candidate_dedup)
        if candidate_dedup.status is StageStatus.FAILED:
            return PipelineItemResult(
                raw=raw,
                stages=tuple(stages),
                candidates=tuple(parsed.output),
                status=StageStatus.FAILED,
                error=candidate_dedup.error,
            )
        candidates = candidate_dedup.output
        persisted: list[dict[str, Any]] = []
        # One raw record may intentionally yield several independent task candidates.
        for candidate in candidates:
            prepared = self.prepare_task(candidate)
            stages.append(prepared)
            if prepared.status is StageStatus.FAILED:
                return PipelineItemResult(
                    raw=raw,
                    stages=tuple(stages),
                    candidates=tuple(candidates),
                    persisted=tuple(persisted),
                    status=StageStatus.FAILED,
                    error=prepared.error,
                )
            sent = self.send_to_database(prepared.output)
            stages.append(sent)
            if sent.status is StageStatus.FAILED:
                return PipelineItemResult(
                    raw=raw,
                    stages=tuple(stages),
                    candidates=tuple(candidates),
                    persisted=tuple(persisted),
                    status=StageStatus.FAILED,
                    error=sent.error,
                )
            if isinstance(sent.output, Mapping):
                persisted.append(dict(sent.output))
            if retained_candidates is not None:
                retained_candidates.append(candidate)
        if not candidates:
            return PipelineItemResult(
                raw=raw,
                stages=tuple(stages),
                candidates=tuple(candidates),
                status=StageStatus.SKIPPED,
            )
        return PipelineItemResult(
            raw=raw,
            stages=tuple(stages),
            candidates=tuple(candidates),
            persisted=tuple(persisted),
        )

    def process_many(self, inputs: Iterable[RawCrawlerInput]) -> PipelineBatchResult:
        inputs = tuple(inputs)
        if not inputs:
            return PipelineBatchResult(items=())

        health = self.check_api_health()
        if health.status is StageStatus.FAILED:
            items = tuple(
                PipelineItemResult(
                    raw=raw,
                    stages=(health,),
                    status=StageStatus.FAILED,
                    error=health.error,
                )
                for raw in inputs
            )
            return PipelineBatchResult(
                items=items,
                status=StageStatus.FAILED,
                error=health.error,
            )

        retained_candidates: list[TaskCandidate] = []
        results: list[PipelineItemResult] = []
        for raw in inputs:
            item = self.process_raw(
                raw,
                api_already_checked=True,
                retained_candidates=retained_candidates,
            )
            results.append(item)
            if self.stop_on_error and item.status is StageStatus.FAILED:
                break
        status = (
            StageStatus.FAILED
            if any(item.status is StageStatus.FAILED for item in results)
            else StageStatus.SUCCESS
        )
        return PipelineBatchResult(items=tuple(results), status=status)

    def process_crawler_results(
        self,
        results: Any,
        captured_at: datetime | None = None,
    ) -> PipelineBatchResult:
        adapted = self.adapt_crawler_results(results, captured_at)
        if adapted.status is StageStatus.FAILED:
            return PipelineBatchResult(items=(), status=StageStatus.FAILED, error=adapted.error)
        batch = self.process_many(adapted.output)
        return PipelineBatchResult(
            items=batch.items,
            adapted=adapted.output,
            status=batch.status,
            error=batch.error,
        )
