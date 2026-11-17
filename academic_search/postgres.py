"""PostgreSQL compilation and row mapping for validated structured requests."""
from collections.abc import Mapping
from datetime import datetime

from .validation import TIME_FIELDS, ValidatedRequest

TASK_FIELDS = (
    "id", "title", "type", "course", "description", "target_audience", "location",
    "registration_start", "registration_end", "start_time", "end_time", "deadline",
    "estimated_hours", "training_points", "drl_category", "recurrence", "status",
    "is_manual", "source_url", "source_platform", "updated_at",
)
SELECT_TASK = "SELECT " + ", ".join(f"t.{field}" for field in TASK_FIELDS) + " FROM tasks AS t"
USER_SCOPE = "EXISTS (SELECT 1 FROM user_tasks AS ut WHERE ut.task_id = t.id AND ut.user_id = %s)"
SORT_COLUMNS = {
    "id": 't.id COLLATE "C"',
    "deadline": "t.deadline",
    "start_time": "t.start_time",
    "updated_at": "t.updated_at",
    "training_points": "t.training_points",
}
DIRECTIONS = {"asc": "ASC", "desc": "DESC"}


def compile_lookup(task_id: str, user_id: int):
    return f'{SELECT_TASK} WHERE t.id COLLATE "C" = %s AND {USER_SCOPE}', [task_id, user_id]


def literal_contains_pattern(term: str):
    """Escape the marker and LIKE wildcards before adding substring wildcards."""
    return "%" + term.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def compile_request(request: ValidatedRequest, user_id: int):
    """Compile bound values without validating or converting aware timestamps."""
    filters = request.filters
    clauses, params = [USER_SCOPE], [user_id]

    def values_clause(column, values):
        clauses.append(f"{column} IN ({', '.join('%s' for _ in values)})")
        params.extend(values)

    values_clause("t.status", filters["statuses"])
    for term in request.terms:
        clauses.append("(t.title ILIKE %s ESCAPE '!' OR t.description ILIKE %s ESCAPE '!')")
        pattern = literal_contains_pattern(term)
        params.extend([pattern, pattern])
    for key, column in (("types", "t.type"), ("source_platforms", "t.source_platform")):
        if key in filters:
            values_clause(column, filters[key])
    for key in ("course", "source_platform", "target_audience"):
        if key in filters:
            clauses.append(f't.{key} COLLATE "C" = %s')
            params.append(filters[key])
    if "location_prefix" in filters:
        clauses.append('left(t.location, char_length(%s)) COLLATE "C" = %s')
        params.extend([filters["location_prefix"], filters["location_prefix"]])
    for key, operator in (("min_training_points", ">="), ("max_training_points", "<=")):
        if key in filters:
            clauses.append(f"t.training_points {operator} %s")
            params.append(filters[key])
    for key, column in (("deadline_within", "deadline"), ("registration_end_within", "registration_end"),
                        ("start_time_within", "start_time"), ("updated_at_within", "updated_at")):
        if key in filters:
            clauses.append(f"(t.{column} >= %s AND t.{column} < %s)")
            params.extend(filters[key])
    if "event_overlaps" in filters:
        start, end = filters["event_overlaps"]
        clauses.append("(t.start_time < t.end_time AND t.start_time < %s AND t.end_time > %s)")
        params.extend([end, start])
    if "registration_open_at" in filters:
        clauses.append("(t.registration_start <= %s AND t.registration_end >= %s)")
        params.extend([filters["registration_open_at"], filters["registration_open_at"]])
    column, direction = SORT_COLUMNS[request.sort], DIRECTIONS[request.direction]
    order = f"{column} {direction}" if request.sort == "id" else f'{column} {direction} NULLS LAST, t.id COLLATE "C" ASC'
    sql = f"{SELECT_TASK} WHERE {' AND '.join(clauses)} ORDER BY {order} LIMIT %s OFFSET %s"
    return sql, [*params, request.limit, request.offset]


def task_record(row):
    """Return exactly the database task fields with aware Python timestamps."""
    if isinstance(row, Mapping):
        result = {field: row[field] for field in TASK_FIELDS}
    else:
        if len(row) != len(TASK_FIELDS):
            raise ValueError("Unexpected PostgreSQL task column count")
        result = dict(zip(TASK_FIELDS, row))
    for field in TIME_FIELDS:
        value = result[field]
        if value is not None and (not isinstance(value, datetime) or value.utcoffset() is None):
            raise ValueError(f"Database {field} must be an aware datetime")
    if result["updated_at"] is None:
        raise ValueError("Database updated_at cannot be null")
    return result
