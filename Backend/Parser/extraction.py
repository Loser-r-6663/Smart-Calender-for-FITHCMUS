"""Prompt construction and provider-to-domain task extraction."""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from string import Template
from typing import Any, Callable

from .errors import ProviderSchemaError, UnsupportedPayloadError
from .models import (
    DRLCategory,
    RawCrawlerInput,
    SourcePlatform,
    TaskCandidate,
    TaskStatus,
    TaskType,
)
from .providers import LLMGateway, parse_envelope


GMT_PLUS_7 = timezone(timedelta(hours=7), name="GMT+07:00")
UNKNOWN_DEADLINE = datetime(2099, 12, 31, 23, 59, 59, tzinfo=GMT_PLUS_7)
_PROMPT_TEMPLATE = Template(
    (Path(__file__).with_name("prompt.txt")).read_text(encoding="utf-8")
)


def normalize_datetime(value: datetime) -> datetime:
    """Represent a datetime in GMT+7, treating naive values as local time."""

    if not isinstance(value, datetime):
        raise TypeError("datetime required")
    # Naive values are local GMT+7; aware values are converted to the same zone.
    if value.tzinfo is None:
        return value.replace(tzinfo=GMT_PLUS_7)
    return value.astimezone(GMT_PLUS_7)


def build_prompt(
    raw_text: str,
    captured_at: datetime,
    source_platform: str | None = None,
    source_alias: str | None = None,
) -> str:
    return _PROMPT_TEMPLATE.substitute(
        captured_at=captured_at.isoformat(),
        source_platform=source_platform or "unknown",
        source_alias=source_alias or "unknown",
        raw_text=raw_text,
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProviderSchemaError("LLM provider returned a non-text string field")
    return value.strip() or None


def _payload_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    raise UnsupportedPayloadError(
        f"unsupported crawler payload type: {type(payload).__name__}"
    )


def _is_portal_source(raw: RawCrawlerInput) -> bool:
    return raw.source_platform == SourcePlatform.PORTAL or (
        isinstance(raw.source_alias, str)
        and raw.source_alias.casefold() == "portal"
    )


def _portal_record(payload: Any) -> Mapping[str, Any] | None:
    try:
        if isinstance(payload, (str, bytes)):
            payload = json.loads(payload)
    except (UnicodeDecodeError, TypeError, ValueError):
        return None
    if not isinstance(payload, Mapping):
        return None
    record = payload.get("record")
    return record if isinstance(record, Mapping) else None


def _raw_text(record: Mapping[str, Any] | None, field: str) -> str | None:
    value = record.get(field) if record is not None else None
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value and value.casefold() != "n/a" else None


def _portal_recurrence(duration: str | None) -> tuple[str | None, str | None]:
    if duration is None:
        return None, None
    room_match = re.search(r"\s*\(([^()]*)\)\s*$", duration)
    room = room_match.group(1).strip() or None if room_match else None
    schedule = duration[:room_match.start()] if room_match else duration
    schedule = re.sub(r"\s*-\s*", "-", schedule.strip())
    schedule = re.sub(
        r"\b(T[2-7])\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\b",
        lambda match: (
            f"{match.group(1)} {int(match.group(2)):02d}:{match.group(3)}-"
            f"{int(match.group(4)):02d}:{match.group(5)}"
        ),
        schedule,
        flags=re.IGNORECASE,
    )
    return schedule or None, room


def _normalize_recurrence(value: str | None) -> str | None:
    if value is None:
        return None
    match = re.fullmatch(
        r"\s*(T[2-7]|CN)\s+(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*",
        value,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    weekday, start_hour, start_minute, end_hour, end_minute = match.groups()
    start = int(start_hour) * 60 + int(start_minute)
    end = int(end_hour) * 60 + int(end_minute)
    if (
        int(start_hour) > 23
        or int(end_hour) > 23
        or int(start_minute) > 59
        or int(end_minute) > 59
        or start >= end
    ):
        return None
    return f"{weekday.upper()} {start_hour.zfill(2)}:{start_minute}-{end_hour.zfill(2)}:{end_minute}"


def _portal_course(
    record: Mapping[str, Any] | None,
    title: str | None,
    provider_course: str | None,
) -> str | None:
    course = _raw_text(record, "Course")
    if course is not None:
        return course
    match = re.match(r"\s*([A-Za-z]{2,}\d{3,}[A-Za-z0-9]*)\b", title or "")
    return match.group(1) if match else provider_course


class LLMExtractor:
    def __init__(
        self,
        client: LLMGateway,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = client
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def parse(
        self,
        raw: RawCrawlerInput,
        text: str | None = None,
    ) -> Sequence[TaskCandidate]:
        captured = normalize_datetime(raw.captured_at or self.clock())
        content = text if text is not None else _payload_text(raw.payload)
        portal = _is_portal_source(raw)
        portal_record = _portal_record(raw.payload) if portal else None
        response = self.client.extract(
            build_prompt(
                content,
                captured,
                raw.source_platform.value if raw.source_platform else None,
                raw.source_alias,
            )
        )
        try:
            # Validate the provider envelope before converting any task fields.
            envelope = parse_envelope(response)
        except Exception as exc:
            if isinstance(exc, ProviderSchemaError):
                raise
            raise ProviderSchemaError(
                "LLM provider response did not match the extraction envelope"
            ) from exc

        result: list[TaskCandidate] = []
        for item in envelope.tasks:
            data = {
                field: _optional_text(getattr(item, field, None))
                for field in (
                    "title", "course", "description", "target_audience",
                    "location", "recurrence",
                )
            }
            if data["title"] is None:
                # Null is safer than guessing a task identity from incomplete output.
                raise ProviderSchemaError("LLM provider returned a task without a title")

            if portal:
                data["type"] = TaskType.CLASS
            else:
                try:
                    data["type"] = TaskType(getattr(item, "type", None))
                except (TypeError, ValueError) as exc:
                    raise ProviderSchemaError(
                        "LLM provider returned an invalid task type"
                    ) from exc

            try:
                category = getattr(item, "drl_category", None)
                data["drl_category"] = (
                    None if category is None else DRLCategory(category)
                )
            except (TypeError, ValueError) as exc:
                raise ProviderSchemaError(
                    "LLM provider returned an invalid DRL category"
                ) from exc

            for field in (
                "registration_start", "registration_end", "start_time",
                "end_time", "deadline",
            ):
                data[field] = getattr(item, field, None)
            data["estimated_hours"] = item.estimated_hours
            points = item.training_points
            if portal or points is None or points <= 0 or data["drl_category"] is None:
                data["training_points"] = 0
                data["drl_category"] = None
            else:
                data["training_points"] = points

            if portal:
                # Portal corrections are deterministic: source fields override model guesses.
                for field in (
                    "registration_start", "registration_end", "start_time",
                    "end_time", "deadline",
                ):
                    data[field] = None
                data["recurrence"], data["location"] = _portal_recurrence(
                    _raw_text(portal_record, "Duration")
                )
                raw_description = _raw_text(portal_record, "Description")
                if raw_description is not None:
                    data["description"] = raw_description
                data["course"] = _portal_course(
                    portal_record,
                    data["title"],
                    data["course"],
                )

            data["recurrence"] = _normalize_recurrence(data["recurrence"])

            for field in (
                "registration_start", "registration_end", "start_time",
                "end_time", "deadline",
            ):
                if data[field] is not None:
                    try:
                        data[field] = normalize_datetime(data[field])
                    except (AttributeError, TypeError, ValueError) as exc:
                        raise ProviderSchemaError(
                            "LLM provider returned an invalid datetime"
                        ) from exc

            result.append(
                TaskCandidate(
                    **data,
                    status=TaskStatus.ACTIVE,
                    is_manual=False,
                    source_url=raw.source_url,
                    source_platform=raw.source_platform or SourcePlatform.CUSTOM,
                    embedding=None,
                    updated_at=captured,
                    id=None,
                )
            )
        return tuple(result)


LLMParser = LLMExtractor
