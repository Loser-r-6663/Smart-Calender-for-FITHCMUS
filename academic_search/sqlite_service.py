"""Parameterized structured search over a normalized SQLite read projection."""
import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from .validation import (SearchValidationError, ValidatedRequest, check,
                         parse_instant, validate_request)

SORT_COLUMNS = {name: name for name in ("id", "deadline", "start_time", "updated_at", "training_points")}
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def validate_task_id(task_id):
    """Keep the SQLite fixture ID contract distinct from Database task IDs."""
    check(isinstance(task_id, str) and re.fullmatch(r"[a-z0-9-]{1,40}", task_id),
          "task_id must contain 1–40 lowercase letters, digits or hyphens")


def sqlite_timestamp(value):
    """Store an aware datetime as exact integer UTC microseconds."""
    delta = value - EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def instant(value):
    """Validate a fixture timestamp and convert it to SQLite storage units."""
    return sqlite_timestamp(parse_instant(value))


@dataclass(frozen=True)
class SQLiteRequest:
    common: ValidatedRequest
    course_code: str | None = None


def validate_sqlite_request(request):
    """Validate the legacy SQLite vocabulary without aliasing course text."""
    if not isinstance(request, Mapping) or not isinstance(request.get("filters", {}), Mapping):
        return SQLiteRequest(validate_request(request))
    filters = dict(request.get("filters", {}))
    check("course" not in filters, "unknown filter")
    course_code = None
    if "course_code" in filters:
        course_code = filters.pop("course_code")
        check(isinstance(course_code, str) and bool(course_code) and len(course_code) <= 100,
              "invalid course_code")
        check(re.fullmatch(r"[A-Z]{3}\d{5}", course_code), "invalid course_code")
    adapted = dict(request)
    adapted["filters"] = filters
    common = validate_request(adapted)
    return SQLiteRequest(common, course_code)


def compile_request(request: SQLiteRequest):
    """Compile a validated SQLite request; perform no request validation."""
    common = request.common
    filters = common.filters
    clauses, params = [], []

    def values_clause(column, values):
        clauses.append(f"{column} IN ({','.join('?' for _ in values)})")
        params.extend(values)

    values_clause("status", filters["statuses"])
    if "types" in filters:
        values_clause("type", filters["types"])
    if "source_platforms" in filters:
        values_clause("source_platform", filters["source_platforms"])
    if request.course_code is not None:
        clauses.append("course_code = ?")
        params.append(request.course_code)
    for key in ("source_platform", "target_audience", "location_prefix"):
        if key not in filters:
            continue
        value = filters[key]
        if key == "location_prefix":
            clauses.append("substr(location, 1, length(?)) = ?")
            params.extend([value, value])
        else:
            clauses.append(f"{key} = ?")
            params.append(value)
    for key, operator in (("min_training_points", ">="), ("max_training_points", "<=")):
        if key in filters:
            clauses.append(f"training_points {operator} ?")
            params.append(filters[key])
    for key, column in (("deadline_within", "deadline"), ("registration_end_within", "registration_end"),
                        ("start_time_within", "start_time"), ("updated_at_within", "updated_at"),
                        ("event_overlaps", None)):
        if key not in filters:
            continue
        start, end = map(sqlite_timestamp, filters[key])
        if column:
            clauses.append(f"({column} >= ? AND {column} < ?)")
            params.extend([start, end])
        else:
            clauses.append("(start_time < end_time AND start_time < ? AND end_time > ?)")
            params.extend([end, start])
    if "registration_open_at" in filters:
        at = sqlite_timestamp(filters["registration_open_at"])
        clauses.append("(registration_start <= ? AND registration_end >= ?)")
        params.extend([at, at])
    column = SORT_COLUMNS[common.sort]
    # Only validated allowlisted names enter SQL. Ties always use ascending ID.
    order = f"{column} {common.direction.upper()}" if common.sort == "id" else f"({column} IS NULL) ASC, {column} {common.direction.upper()}, id ASC"
    sql = f"SELECT payload FROM search_tasks WHERE {' AND '.join(clauses)} ORDER BY {order} LIMIT ? OFFSET ?"
    return sql, [*params, common.limit, common.offset]


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
        sql, params = compile_request(validate_sqlite_request(request))
        return [json.loads(row[0]) for row in self.connection.execute(sql, params)]
