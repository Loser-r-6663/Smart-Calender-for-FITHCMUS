"""Deterministic keyword matching over an authorized Search record collection."""

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta, timezone
from types import MappingProxyType

from .records import SearchRecord

VN_TZ = timezone(timedelta(hours=7))
TASK_TYPES = ("class", "assignment", "event", "announcement", "personal")
SORTS = ("best_match", "soonest_deadline", "latest_deadline", "title")
POINT_PREFIX = r"lớn hơn|nhiều hơn|nhỏ hơn|bé hơn|ít hơn|nhiều nhất|ít nhất|tối thiểu|tối đa|hơn|trên|dưới|từ|bằng"
POINT_SUFFIX = r"trở lên|trở xuống"
POINTS = re.compile(
    rf"(?<!\w)(?:(?P<prefix>{POINT_PREFIX})\s+)?(?P<number>[0-9]+)\s+"
    rf"(?:điểm rèn luyện|đrl|điểm)(?!\w)(?:\s+(?P<suffix>{POINT_SUFFIX})(?!\w))?", re.I
)
EVENT = re.compile(r"(?<!\w)sự kiện(?!\w)", re.I)
NEGATION = re.compile(r"(?<!\w)(?:không|chẳng|chưa)(?!\w)", re.I)
UNSUPPORTED_PREFIX = re.compile(
    rf"(?<!\w)(?:không(?: phải)?|chẳng(?: phải)?|chưa|{POINT_PREFIX}|đến)\s*$", re.I
)
UNSUPPORTED_SUFFIX = re.compile(rf"^\s*(?:{POINT_SUFFIX}|đến\s+[0-9]|[-–—]\s*[0-9])", re.I)


class SearchFilterError(ValueError):
    """The query, filters, or sort cannot be applied."""


@dataclass(frozen=True)
class SearchResults:
    hits: tuple[SearchRecord, ...]
    eligible_records: tuple[SearchRecord, ...]
    effective_filters: Mapping
    topic: str
    sort: str


def _require(condition, message):
    if not condition:
        raise SearchFilterError(message)


def _calendar_date(value):
    if type(value) is date:
        return value
    _require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
             "Deadline bounds must be dates or YYYY-MM-DD strings")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise SearchFilterError("Invalid deadline date") from error


def _filters(selected):
    _require(isinstance(selected, Mapping), "filters must be a mapping")
    _require(set(selected) <= {"types", "course", "min_training_points", "max_training_points",
                               "deadline_start", "deadline_end"}, "Unknown filter")
    result = dict(selected)
    types = result.get("types", TASK_TYPES)
    _require(isinstance(types, (list, tuple)) and bool(types)
             and all(isinstance(value, str) and value in TASK_TYPES for value in types),
             "types must contain supported task types")
    _require(len(types) == len(set(types)), "Duplicate task types")
    result["types"] = tuple(types)
    if "course" in result:
        _require(isinstance(result["course"], str) and bool(result["course"].strip()), "Invalid course")
    for key in ("min_training_points", "max_training_points"):
        if key in result:
            _require(type(result[key]) is int and 0 <= result[key] <= 100,
                     "Training points must be integers from 0 through 100")
    for key in ("deadline_start", "deadline_end"):
        if key in result:
            result[key] = _calendar_date(result[key])
    _require(result.get("deadline_start", date.min) <= result.get("deadline_end", date.max),
             "Reversed deadline range")
    _require(result.get("min_training_points", 0) <= result.get("max_training_points", 100),
             "Conflicting training-point constraints")
    return result


def _interpret(query, filters):
    text = " ".join(unicodedata.normalize("NFC", query).split())
    matches = list(POINTS.finditer(text))
    _require(len(matches) <= 1, "Ambiguous query: multiple training-point expressions")
    if not matches:
        return text
    match = matches[0]
    before, after = text[:match.start()], text[match.end():]
    _require(not ((match["prefix"] and match["suffix"])
                  or NEGATION.search(text) or re.search(r"[0-9.,+\-–—<>=≤≥]\s*$", before)
                  or UNSUPPORTED_PREFIX.search(before) or UNSUPPORTED_SUFFIX.search(after)),
             "Unsupported training-point expression; use one equality, strict, minimum, or maximum comparison")
    digits = match["number"].lstrip("0") or "0"
    _require(len(digits) <= 3 and int(digits) <= 100, "Training points exceed 100")
    number = int(digits)
    comparison = (match["prefix"] or match["suffix"] or "bằng").casefold()
    # Integer points convert strict comparisons to inclusive bounds without clamping.
    if comparison in ("bằng", "hơn", "lớn hơn", "nhiều hơn", "trên", "từ", "ít nhất", "tối thiểu", "trở lên"):
        minimum = number + (comparison in ("hơn", "lớn hơn", "nhiều hơn", "trên"))
        filters["min_training_points"] = max(filters.get("min_training_points", 0), minimum)
    if comparison in ("bằng", "ít hơn", "nhỏ hơn", "bé hơn", "dưới", "nhiều nhất", "tối đa", "trở xuống"):
        maximum = number - (comparison in ("ít hơn", "nhỏ hơn", "bé hơn", "dưới"))
        filters["max_training_points"] = min(filters.get("max_training_points", 100), maximum)
    _require(filters.get("min_training_points", 0) <= filters.get("max_training_points", 100),
             "Conflicting training-point constraints")
    spans = [(match.start(), match.end())]
    event_matches = list(EVENT.finditer(text))
    if event_matches:
        _require("event" in filters["types"], "Conflicting task types")
        filters["types"] = ("event",)
        spans.extend((item.start(), item.end()) for item in event_matches)
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + " " + text[end:]
    return " ".join(text.split())


def _eligible(record, filters):
    if record.type not in filters["types"]:
        return False
    if "course" in filters and (record.course or "").casefold() != filters["course"].casefold():
        return False
    for key, below in (("min_training_points", True), ("max_training_points", False)):
        if key in filters:
            points = record.training_points
            if points is None or (points < filters[key] if below else points > filters[key]):
                return False
    if "deadline_start" in filters or "deadline_end" in filters:
        if record.deadline is None:
            return False
        local_date = record.deadline.astimezone(VN_TZ).date()
        if not filters.get("deadline_start", date.min) <= local_date <= filters.get("deadline_end", date.max):
            return False
    return True


def _match_rank(record, topic, terms):
    if not topic:
        return 0
    title = record.title.casefold()
    if topic == title or topic == (record.course or "").casefold():
        return 0
    if all(term in title for term in terms):
        return 1
    description = (record.description or "").casefold()
    if all(term in title or term in description for term in terms):
        return 2
    return 3


def search_records(
    records: Iterable[SearchRecord], query: str = "", *, filters: Mapping | None = None,
    sort: str | None = None,
) -> SearchResults:
    """Match snapshot.records without fetching or mutation.

    Filters accept types, course, min/max_training_points, and inclusive
    deadline_start/deadline_end dates. Sorts are best_match, soonest_deadline,
    latest_deadline, and title. Eligible records retain input order.
    """
    _require(isinstance(query, str) and "\x00" not in query, "query must be text without NUL")
    effective = _filters({} if filters is None else filters)
    topic = _interpret(query, effective)
    order = sort if sort is not None else ("best_match" if topic else "soonest_deadline")
    _require(isinstance(order, str) and order in SORTS, "Unknown sort order")
    eligible = tuple(record for record in records if _eligible(record, effective))
    folded = topic.casefold()
    terms = folded.split()
    hits = [record for record in eligible if not topic or _match_rank(record, folded, terms) < 3]
    hits.sort(key=lambda record: record.key)
    if order == "best_match":
        hits.sort(key=lambda record: _match_rank(record, folded, terms))
    elif order == "title":
        hits.sort(key=lambda record: record.title.casefold())
    else:
        dated = [record for record in hits if record.deadline is not None]
        undated = [record for record in hits if record.deadline is None]
        dated.sort(key=lambda record: record.deadline, reverse=order == "latest_deadline")
        hits = dated + undated
    return SearchResults(tuple(hits), eligible, MappingProxyType(effective), topic, order)
