"""Database-independent structured request validation and normalization."""
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType

TYPES = frozenset({"class", "assignment", "exam", "event", "personal", "tuition"})
STATUSES = frozenset({"active", "done", "archived", "cancelled"})
SOURCES = frozenset({"moodle", "portal", "facebook", "custom"})
SORTS = frozenset({"id", "deadline", "start_time", "updated_at", "training_points"})
TIME_FIELDS = ("deadline", "registration_start", "registration_end", "start_time", "end_time", "updated_at")
FILTER_KEYS = frozenset({"types", "course", "source_platform", "source_platforms", "statuses",
                         "min_training_points", "max_training_points", "deadline_within",
                         "registration_open_at", "registration_end_within", "start_time_within",
                         "event_overlaps", "updated_at_within", "target_audience", "location_prefix"})


class SearchValidationError(ValueError):
    """The request cannot be executed because its structured inputs are invalid."""


def check(condition, message):
    if not condition:
        raise SearchValidationError(message)


def validate_task_id(task_id):
    """Normalize an ID using the Database TaskData text/length rules."""
    check(isinstance(task_id, str), "task_id must be a string")
    task_id = task_id.strip()
    check(1 <= len(task_id) <= 64 and "\x00" not in task_id,
          "task_id must contain 1–64 characters without NUL")
    return task_id


def parse_instant(value):
    """Validate an ISO timestamp and return an aware UTC datetime."""
    check(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", value),
        "timestamp must be ISO 8601 with seconds and an explicit timezone")
    try:
        # Normalize Z explicitly for Python 3.10 compatibility.
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise SearchValidationError(f"invalid timestamp: {value}") from error


def enum_list(value, allowed, name):
    check(isinstance(value, list) and bool(value), f"{name} must be a nonempty list; omit it for the default")
    check(all(isinstance(item, str) and item in allowed for item in value), f"invalid {name}")
    check(len(value) == len(set(value)), f"duplicate {name}")
    return tuple(value)


@dataclass(frozen=True)
class ValidatedRequest:
    filters: Mapping
    sort: str
    direction: str
    limit: int
    offset: int


def validate_request(request):
    """Return a detached, immutable request without accessing a database."""
    check(isinstance(request, Mapping), "request must be a mapping")
    check(set(request) <= {"filters", "sort", "direction", "limit", "offset"}, "unknown request field; text search is unsupported")
    filters = request.get("filters", {})
    check(isinstance(filters, Mapping) and set(filters) <= FILTER_KEYS, "unknown filter")
    sort = request.get("sort", "deadline")
    direction = request.get("direction", "asc")
    check(isinstance(sort, str) and sort in SORTS, "invalid sort")
    check(isinstance(direction, str) and direction in {"asc", "desc"}, "direction must be asc or desc")
    limit, offset = request.get("limit", 20), request.get("offset", 0)
    check(type(limit) is int and 1 <= limit <= 100, "limit must be an integer from 1 to 100")
    check(type(offset) is int and 0 <= offset <= 100_000, "offset must be an integer from 0 to 100000")
    normalized = {"statuses": enum_list(filters.get("statuses", ["active"]), STATUSES, "statuses")}
    for key, allowed in (("types", TYPES), ("source_platforms", SOURCES)):
        if key in filters:
            normalized[key] = enum_list(filters[key], allowed, key)
    for key in ("course", "source_platform", "target_audience", "location_prefix"):
        if key not in filters:
            continue
        value = filters[key]
        if key == "course":
            check(isinstance(value, str) and bool(value.strip()) and "\x00" not in value, "invalid course")
        else:
            check(isinstance(value, str) and bool(value) and len(value) <= 100, f"invalid {key}")
        if key == "source_platform":
            check(value in SOURCES, "invalid source_platform")
        normalized[key] = value
    for key in ("min_training_points", "max_training_points"):
        if key in filters:
            value = filters[key]
            check(type(value) is int and 0 <= value <= 100, f"{key} must be an integer from 0 to 100")
            normalized[key] = value
    if "min_training_points" in filters and "max_training_points" in filters:
        check(filters["min_training_points"] <= filters["max_training_points"], "reversed training points range")
    for key in ("deadline_within", "registration_end_within", "start_time_within",
                "updated_at_within", "event_overlaps"):
        if key not in filters:
            continue
        value = filters[key]
        check(isinstance(value, (list, tuple)) and len(value) == 2, f"{key} requires two timestamps")
        start, end = map(parse_instant, value)
        check(start < end, f"{key} requires start < end")
        normalized[key] = (start, end)
    if "registration_open_at" in filters:
        normalized["registration_open_at"] = parse_instant(filters["registration_open_at"])
    return ValidatedRequest(MappingProxyType(normalized), sort, direction, limit, offset)
