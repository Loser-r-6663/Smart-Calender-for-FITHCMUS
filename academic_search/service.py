"""Parameterized structured search over a normalized SQLite read projection."""
import json
import re
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone

TYPES = frozenset({"class", "assignment", "exam", "event", "personal", "tuition"})
STATUSES = frozenset({"active", "done", "archived", "cancelled"})
SOURCES = frozenset({"moodle", "portal", "facebook", "custom"})
SORT_COLUMNS = {name: name for name in ("id", "deadline", "start_time", "updated_at", "training_points")}
TIME_FIELDS = ("deadline", "registration_start", "registration_end", "start_time", "end_time", "updated_at")
FILTER_KEYS = frozenset({"types", "course_code", "source_platform", "source_platforms", "statuses",
                         "min_training_points", "max_training_points", "deadline_within",
                         "registration_open_at", "registration_end_within", "start_time_within",
                         "event_overlaps", "updated_at_within", "target_audience", "location_prefix"})
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class SearchValidationError(ValueError):
    """The request cannot be executed because its structured inputs are invalid."""


def check(condition, message):
    if not condition:
        raise SearchValidationError(message)


def validate_task_id(task_id):
    check(isinstance(task_id, str) and re.fullmatch(r"[a-z0-9-]{1,40}", task_id),
          "task_id must contain 1–40 lowercase letters, digits or hyphens")


def instant(value):
    """Convert an aware ISO timestamp to exact integer UTC microseconds."""
    check(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", value),
        "timestamp must be ISO 8601 with seconds and an explicit timezone")
    try:
        # Normalize Z explicitly for Python 3.10 compatibility.
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        delta = parsed.astimezone(timezone.utc) - EPOCH
    except (ValueError, OverflowError) as error:
        raise SearchValidationError(f"invalid timestamp: {value}") from error
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def enum_list(value, allowed, name):
    check(isinstance(value, list) and bool(value), f"{name} must be a nonempty list; omit it for the default")
    check(all(isinstance(item, str) and item in allowed for item in value), f"invalid {name}")
    check(len(value) == len(set(value)), f"duplicate {name}")
    return value


def compile_request(request):
    check(isinstance(request, Mapping), "request must be a mapping")
    check(set(request) <= {"filters", "sort", "direction", "limit", "offset"}, "unknown request field; text search is unsupported")
    filters = request.get("filters", {})
    check(isinstance(filters, Mapping) and set(filters) <= FILTER_KEYS, "unknown filter")
    sort = request.get("sort", "deadline")
    direction = request.get("direction", "asc")
    check(isinstance(sort, str) and sort in SORT_COLUMNS, "invalid sort")
    check(isinstance(direction, str) and direction in {"asc", "desc"}, "direction must be asc or desc")
    limit, offset = request.get("limit", 20), request.get("offset", 0)
    check(type(limit) is int and 1 <= limit <= 100, "limit must be an integer from 1 to 100")
    check(type(offset) is int and 0 <= offset <= 100_000, "offset must be an integer from 0 to 100000")
    clauses, params = [], []

    def values_clause(column, values):
        clauses.append(f"{column} IN ({','.join('?' for _ in values)})")
        params.extend(values)

    values_clause("status", enum_list(filters.get("statuses", ["active"]), STATUSES, "statuses"))
    if "types" in filters:
        values_clause("type", enum_list(filters["types"], TYPES, "types"))
    if "source_platforms" in filters:
        values_clause("source_platform", enum_list(filters["source_platforms"], SOURCES, "source_platforms"))
    for key in ("course_code", "source_platform", "target_audience", "location_prefix"):
        if key not in filters:
            continue
        value = filters[key]
        check(isinstance(value, str) and bool(value) and len(value) <= 100, f"invalid {key}")
        if key == "course_code":
            check(re.fullmatch(r"[A-Z]{3}\d{5}", value), "invalid course_code")
        if key == "source_platform":
            check(value in SOURCES, "invalid source_platform")
        if key == "location_prefix":
            clauses.append("substr(location, 1, length(?)) = ?")
            params.extend([value, value])
        else:
            clauses.append(f"{key} = ?")
            params.append(value)
    for key, operator in (("min_training_points", ">="), ("max_training_points", "<=")):
        if key in filters:
            value = filters[key]
            check(type(value) is int and 0 <= value <= 100, f"{key} must be an integer from 0 to 100")
            clauses.append(f"training_points {operator} ?")
            params.append(value)
    if "min_training_points" in filters and "max_training_points" in filters:
        check(filters["min_training_points"] <= filters["max_training_points"], "reversed training points range")
    for key, column in (("deadline_within", "deadline"), ("registration_end_within", "registration_end"),
                        ("start_time_within", "start_time"), ("updated_at_within", "updated_at"),
                        ("event_overlaps", None)):
        if key not in filters:
            continue
        value = filters[key]
        check(isinstance(value, (list, tuple)) and len(value) == 2, f"{key} requires two timestamps")
        start, end = map(instant, value)
        check(start < end, f"{key} requires start < end")
        if column:
            clauses.append(f"({column} >= ? AND {column} < ?)")
            params.extend([start, end])
        else:
            clauses.append("(start_time < end_time AND start_time < ? AND end_time > ?)")
            params.extend([end, start])
    if "registration_open_at" in filters:
        at = instant(filters["registration_open_at"])
        clauses.append("(registration_start <= ? AND registration_end >= ?)")
        params.extend([at, at])
    column = SORT_COLUMNS[sort]
    # Only allowlisted identifiers and directions enter SQL text. ID is always
    # the final ascending tie-breaker, even when the primary sort is descending.
    order = f"{column} {direction.upper()}" if sort == "id" else f"({column} IS NULL) ASC, {column} {direction.upper()}, id ASC"
    sql = f"SELECT payload FROM search_tasks WHERE {' AND '.join(clauses)} ORDER BY {order} LIMIT ? OFFSET ?"
    return sql, [*params, limit, offset]


class SearchService:
    """Return task dictionaries; let sqlite3.Error propagate distinctly from [].

    The caller owns connection lifetime and transactions. This service performs
    no schema creation, writes, commits, or implicit retries.
    """

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get_task_by_id(self, task_id):
        """Exact lookup across all statuses; return None when the ID is absent."""
        validate_task_id(task_id)
        row = self.connection.execute("SELECT payload FROM search_tasks WHERE id = ?", (task_id,)).fetchone()
        return None if row is None else json.loads(row[0])

    def search_tasks(self, request):
        """Return a bounded, deterministically ordered list of matching tasks."""
        sql, params = compile_request(request)
        return [json.loads(row[0]) for row in self.connection.execute(sql, params)]
