"""Traceable orchestration of extraction, deduplication, and REST persistence."""

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import os
from datetime import datetime
import time
from typing import Any, Callable, Iterable, Mapping

from .adapters import adapt_crawl_results
from .api_client import DatabaseApiClient
from .deduplication import (
    deduplicate_task_candidates,
    JsonRawFingerprintStore,
    RawDedupAction,
    RawDuplicateChecker,
    RawFingerprint,
)
from .extraction import LLMExtractor, UNKNOWN_DEADLINE
from .models import RawCrawlerInput, TaskCandidate
from .providers import create_llm_gateway


class StageStatus(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


class PipelineStage(str, Enum):
    ADAPT = "adapt"
    DUPLICATE = "duplicate"
    PARSE = "parse"
    CANDIDATE_DEDUP = "candidate_dedup"
    PREPARE = "prepare"
    API_HEALTH = "api_health"
    SEND = "send"
    REMEMBER = "remember"


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
        duplicate_checker: RawDuplicateChecker,
        database_api: DatabaseApiClient | None = None,
        stop_on_error: bool = False,
        id_factory: Callable[[RawFingerprint, int], str] | None = None,
    ) -> None:
        self.extractor = extractor
        self.duplicate_checker = duplicate_checker
        self.database_api = database_api
        self.stop_on_error = stop_on_error
        self.id_factory = id_factory or self._default_id

    @staticmethod
    def _default_id(fingerprint: RawFingerprint, candidate_index: int) -> str:
        # Content plus candidate position gives a deterministic id for each task.
        value = f"{fingerprint.content_hash}:{candidate_index}"
        return "task-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]

    @classmethod
    def from_env(cls, **kwargs: Any) -> "ParserManager":
        database_api = DatabaseApiClient()
        extractor = LLMExtractor(create_llm_gateway())
        checker = RawDuplicateChecker(
            JsonRawFingerprintStore(
                os.getenv("PARSER_DEDUP_STATE_PATH", ".parser-dedup.json")
            )
        )
        return cls(extractor, checker, database_api, **kwargs)

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

    def check_duplicate(self, raw: RawCrawlerInput) -> StageResult:
        return self._stage(
            PipelineStage.DUPLICATE,
            raw,
            lambda: self.duplicate_checker.check(raw),
        )

    def parse(self, raw: RawCrawlerInput) -> StageResult:
        return self._stage(
            PipelineStage.PARSE,
            raw,
            lambda: tuple(self.extractor.parse(raw)),
        )

    def deduplicate_candidates(
        self, candidates: tuple[TaskCandidate, ...]
    ) -> StageResult:
        return self._stage(
            PipelineStage.CANDIDATE_DEDUP,
            candidates,
            lambda: deduplicate_task_candidates(candidates),
        )

    def prepare_task(
        self,
        candidate: TaskCandidate,
        fingerprint: RawFingerprint,
        candidate_index: int,
    ) -> StageResult:
        stage_input = {
            "candidate": candidate,
            "fingerprint": fingerprint,
            "candidate_index": candidate_index,
        }

        def prepare() -> dict[str, Any]:
            fields = (
                "title", "type", "course", "description", "target_audience",
                "location", "registration_start", "registration_end", "start_time",
                "end_time", "deadline", "estimated_hours", "training_points",
                "drl_category", "recurrence", "status", "is_manual", "source_url",
                "source_platform", "updated_at",
            )
            data = {field: getattr(candidate, field) for field in fields}
            if (
                candidate.type.value in {"assignment", "tuition"}
                and candidate.deadline is None
            ):
                # Temporary cross-component sentinel; the scheduler must treat this as unknown.
                data["deadline"] = UNKNOWN_DEADLINE
            data["id"] = self.id_factory(fingerprint, candidate_index)
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

    def remember_fingerprint(self, fingerprint: RawFingerprint) -> StageResult:
        return self._stage(
            PipelineStage.REMEMBER,
            fingerprint,
            lambda: self.duplicate_checker.remember(fingerprint),
        )

    def process_raw(
        self,
        raw: RawCrawlerInput,
        api_already_checked: bool = False,
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

        duplicate = self.check_duplicate(raw)
        stages.append(duplicate)
        if duplicate.status is StageStatus.FAILED:
            return PipelineItemResult(
                raw=raw,
                stages=tuple(stages),
                status=StageStatus.FAILED,
                error=duplicate.error,
            )
        if duplicate.output.action is RawDedupAction.SKIP:
            return PipelineItemResult(
                raw=raw,
                stages=tuple(stages),
                status=StageStatus.SKIPPED,
            )

        parsed = self.parse(raw)
        stages.append(parsed)
        candidates = (
            parsed.output if parsed.status is StageStatus.SUCCESS else ()
        )
        if parsed.status is StageStatus.FAILED:
            return PipelineItemResult(
                raw=raw,
                stages=tuple(stages),
                candidates=tuple(candidates),
                status=StageStatus.FAILED,
                error=parsed.error,
            )

        candidate_dedup = self.deduplicate_candidates(parsed.output)
        stages.append(candidate_dedup)
        candidates = (
            candidate_dedup.output
            if candidate_dedup.status is StageStatus.SUCCESS
            else ()
        )
        if candidate_dedup.status is StageStatus.FAILED:
            return PipelineItemResult(
                raw=raw,
                stages=tuple(stages),
                candidates=tuple(candidates),
                status=StageStatus.FAILED,
                error=candidate_dedup.error,
            )

        persisted: list[dict[str, Any]] = []
        # One raw record may intentionally yield several independent task candidates.
        for index, candidate in enumerate(candidates, 1):
            prepared = self.prepare_task(
                candidate,
                duplicate.output.fingerprint,
                index,
            )
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

        if not candidates:
            remembered = self.remember_fingerprint(duplicate.output.fingerprint)
            stages.append(remembered)
            if remembered.status is StageStatus.FAILED:
                return PipelineItemResult(
                    raw=raw,
                    stages=tuple(stages),
                    status=StageStatus.FAILED,
                    error=remembered.error,
                )
            return PipelineItemResult(
                raw=raw,
                stages=tuple(stages),
                candidates=tuple(candidates),
                status=StageStatus.SKIPPED,
            )

        # Remember input only after every candidate has persisted successfully.
        remembered = self.remember_fingerprint(duplicate.output.fingerprint)
        stages.append(remembered)
        if remembered.status is StageStatus.FAILED:
            return PipelineItemResult(
                raw=raw,
                stages=tuple(stages),
                candidates=tuple(candidates),
                persisted=tuple(persisted),
                status=StageStatus.FAILED,
                error=remembered.error,
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

        results: list[PipelineItemResult] = []
        for raw in inputs:
            item = self.process_raw(raw, api_already_checked=True)
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
