"""Plain-text presentation of existing Search requests, metadata and records."""
from datetime import datetime, timedelta, timezone

from academic_search.validation import validate_request

GMT7 = timezone(timedelta(hours=7))
FILTER_LABELS = {
    "statuses": "Status", "types": "Type", "course": "Course",
    "source_platform": "Source platform", "source_platforms": "Source platforms",
    "target_audience": "Target audience", "location_prefix": "Location prefix",
    "deadline_within": "Due within [start, end)",
    "registration_open_at": "Registration open at",
    "registration_end_within": "Registration closes within [start, end)",
    "start_time_within": "Starts within [start, end)",
    "event_overlaps": "Interval overlaps", "updated_at_within": "Updated within [start, end)",
}


class SearchOutputError(ValueError):
    """A returned value cannot be safely represented as a valid task timestamp."""


def timestamp(value):
    if value is None:
        return "Not provided"
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise SearchOutputError("A task timestamp is invalid or lacks a timezone")
    local = value.astimezone(GMT7)
    precision = "microseconds" if local.microsecond else "seconds"
    return local.replace(tzinfo=None).isoformat(sep=" ", timespec=precision) + " GMT+7"


def filter_value(value):
    if isinstance(value, datetime):
        return timestamp(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(filter_value(item) for item in value)
    return str(value)


def filter_lines(filters):
    lines = []
    for key, value in filters.items():
        if key not in {"min_training_points", "max_training_points"}:
            lines.append(f"  {FILTER_LABELS.get(key, key.replace('_', ' ').capitalize())}: {filter_value(value)}")
    if "types" not in filters:
        lines.append("  Type: all six task types")
    minimum, maximum = filters.get("min_training_points"), filters.get("max_training_points")
    if minimum is not None and maximum is not None:
        points = f"exactly {minimum}" if minimum == maximum else f"{minimum} through {maximum}"
    elif minimum is not None:
        points = f"at least {minimum}"
    elif maximum is not None:
        points = f"at most {maximum}"
    else:
        points = None
    if points is not None:
        lines.append("  Training points: " + points)
    return lines


def keyword(value):
    return value if value.strip() else "No keyword constraint."


def render_search(request, rows, metadata=None):
    original = metadata.original_query if metadata is not None else request.get("keyword", "")
    lines = ["Original query: " + keyword(original)]
    if metadata is not None:
        lines.extend(["Mode: interpreted", "Remaining keyword: " + keyword(metadata.remaining_keyword),
                      "Effective filters:"])
        filters = metadata.effective_filters
    else:
        lines.extend(["Mode: literal keyword search", "Selected filters (including defaults):"])
        filters = request.get("filters", {})
    lines.extend(filter_lines(validate_request({"filters": filters}).filters))
    lines.extend(["", f"Returned page: {len(rows)} task(s)"])
    if not rows:
        lines.append("No matching tasks")
    for task in rows:
        points = task.get("training_points")
        lines.extend(["", "Task ID: " + task["id"], "Title: " + task["title"],
                      "Type: " + task["type"], f"Training points: {points if points is not None else 'Unknown'}"])
        if task["type"] in {"assignment", "tuition"} or task.get("deadline") is not None:
            lines.append("Due: " + timestamp(task.get("deadline")))
        if (task["type"] in {"event", "class", "exam", "personal"}
                or task.get("start_time") is not None or task.get("end_time") is not None):
            lines.extend(["Starts: " + timestamp(task.get("start_time")),
                          "Ends: " + timestamp(task.get("end_time"))])
        if task.get("registration_end") is not None:
            lines.append("Registration closes: " + timestamp(task["registration_end"]))
    return "\n".join(lines)
