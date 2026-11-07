"""Adapt crawler manager output into deterministic raw parser envelopes."""

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
import json
from typing import Any

from .errors import ParserError
from .models import RawCrawlerInput, SourcePlatform


class CrawlerAdapterError(ParserError):
    """Raised when crawler output cannot be adapted safely."""


_RAW_TASK_FIELDS = (
    "Title", "Type", "Description", "CreateDate", "Duration", "Deadline",
    "Course", "Content", "Link",
)
_PLATFORMS = {
    "portal": SourcePlatform.PORTAL,
    "moodle": SourcePlatform.MOODLE,
    "fb": SourcePlatform.FACEBOOK,
}


def _json_value(value: Any) -> Any:
    if value == "N/A":
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise CrawlerAdapterError("record mappings must use string keys")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise CrawlerAdapterError(
        f"record contains unsupported value type: {type(value).__name__}"
    )


def _record_data(record: object) -> Mapping[str, Any]:
    if isinstance(record, Mapping):
        return record
    for method_name in ("model_dump", "dict"):
        method = getattr(record, method_name, None)
        if callable(method):
            try:
                data = method()
            except Exception as exc:
                raise CrawlerAdapterError(
                    f"record {method_name}() failed"
                ) from exc
            if isinstance(data, Mapping):
                return data
            raise CrawlerAdapterError(
                f"record {method_name}() did not return a mapping"
            )
    fields = {
        field: getattr(record, field)
        for field in _RAW_TASK_FIELDS
        if hasattr(record, field)
    }
    if fields:
        return fields
    raise CrawlerAdapterError(f"unsupported record shape: {type(record).__name__}")


def _source_url(data: Mapping[str, Any]) -> str | None:
    for field in ("Link", "link", "source_url"):
        value = data.get(field)
        if isinstance(value, str) and value and value != "N/A":
            return value
    return None


def adapt_crawl_results(
    results: Mapping[str, Sequence[object]],
    *,
    captured_at: datetime | None = None,
) -> tuple[RawCrawlerInput, ...]:
    """Flatten source lists into parser-compatible JSON envelopes."""

    if not isinstance(results, Mapping):
        raise CrawlerAdapterError("crawler results must be a mapping")
    captured_at = captured_at or datetime.now(timezone.utc)
    if not isinstance(captured_at, datetime):
        raise CrawlerAdapterError("captured_at must be a datetime or None")

    adapted: list[RawCrawlerInput] = []
    for source_alias, records in results.items():
        if not isinstance(source_alias, str):
            raise CrawlerAdapterError("crawler source keys must be strings")
        if isinstance(records, (str, bytes, bytearray)) or not isinstance(records, Sequence):
            raise CrawlerAdapterError(
                f"crawler source {source_alias!r} must contain a sequence of records"
            )
        platform = _PLATFORMS.get(source_alias.casefold(), SourcePlatform.CUSTOM)
        for record in records:
            data = _record_data(record)
            envelope = {
                "record": _json_value(data),
                "source": {"alias": source_alias, "platform": platform.value},
            }
            adapted.append(
                RawCrawlerInput(
                    payload=json.dumps(
                        envelope,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    source_platform=platform,
                    source_alias=source_alias,
                    captured_at=captured_at,
                    source_url=_source_url(data),
                )
            )
    return tuple(adapted)
