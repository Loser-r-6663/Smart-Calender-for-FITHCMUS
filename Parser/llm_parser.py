"""Convert provider DTOs into immutable TaskCandidate values."""

from datetime import datetime, timezone
from typing import Any, Callable, Sequence

from .errors import ProviderSchemaError, UnsupportedPayloadError
from .extraction_schema import parse_envelope
from .gemini_client import GeminiGateway
from .models import RawCrawlerInput, SourcePlatform, TaskCandidate, TaskStatus, TaskType
from .prompts import build_prompt
from .time import normalize_datetime


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProviderSchemaError("Gemini returned a non-text string field")
    value = value.strip()
    return value or None


def _payload_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    raise UnsupportedPayloadError(f"unsupported crawler payload type: {type(payload).__name__}")


class LLMParser:
    def __init__(self, client: GeminiGateway, clock: Callable[[], datetime] | None = None) -> None:
        self.client = client
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def parse(self, raw: RawCrawlerInput, text: str | None = None) -> Sequence[TaskCandidate]:
        captured = normalize_datetime(raw.captured_at or self.clock())
        content = text if text is not None else _payload_text(raw.payload)
        envelope = self.client.extract(build_prompt(content, captured, raw.source_platform.value if raw.source_platform else None, raw.source_alias))
        try:
            envelope = parse_envelope(envelope)
            tasks = envelope.tasks
        except Exception as exc:
            raise ProviderSchemaError("Gemini response did not match the extraction envelope") from exc
        result: list[TaskCandidate] = []
        for item in tasks:
            data = {field: _optional_text(getattr(item, field, None)) for field in (
                "title", "course_code", "description", "target_audience", "location",
                "recurrence")}
            try:
                data["type"] = TaskType(getattr(item, "type", None))
            except (TypeError, ValueError) as exc:
                raise ProviderSchemaError("Gemini returned an invalid task type") from exc
            if data["title"] is None:
                raise ProviderSchemaError("Gemini returned a task without a title")
            for field in ("registration_start", "registration_end", "start_time", "end_time", "deadline"):
                data[field] = getattr(item, field, None)
            data["estimated_hours"] = getattr(item, "estimated_hours", None)
            data["training_points"] = getattr(item, "training_points", None)
            for field in ("registration_start", "registration_end", "start_time", "end_time", "deadline"):
                if data[field] is not None:
                    try:
                        data[field] = normalize_datetime(data[field])
                    except (AttributeError, TypeError, ValueError) as exc:
                        raise ProviderSchemaError("Gemini returned an invalid datetime") from exc
            result.append(TaskCandidate(**data, drl_category=None, status=TaskStatus.ACTIVE,
                is_manual=False, source_url=raw.source_url, source_platform=raw.source_platform or SourcePlatform.CUSTOM,
                embedding=None, updated_at=captured, id=None))
        return tuple(result)


StructuredExtractor = LLMParser
