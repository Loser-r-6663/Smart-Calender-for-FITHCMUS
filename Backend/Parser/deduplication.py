"""Parsed task-candidate deduplication primitives."""

from collections.abc import Sequence
from datetime import datetime
from difflib import SequenceMatcher
from enum import Enum
import re
import unicodedata

from .errors import ParserError
from .models import TaskCandidate


class CandidateDeduplicationError(ParserError):
    """Raised when parsed task candidates cannot be safely deduplicated."""


TEXT_SIMILARITY_THRESHOLD = 0.75
_WHITESPACE = re.compile(r"\s+")
_DATE_TIME_FIELDS = (
    "registration_start", "registration_end", "start_time", "end_time", "deadline"
)
_TASK_DETAIL_FIELDS = ("type", "course", "location")


def _clean_text(value: str) -> str:
    # Use the same Unicode form, spacing, and capitalization for text comparisons.
    cleaned = unicodedata.normalize("NFKC", value)
    return _WHITESPACE.sub(" ", cleaned).strip().casefold()


def _value_for_comparison(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value
    return _clean_text(value) if isinstance(value, str) else value


def _has_different_date_or_time(candidate: TaskCandidate, previous: TaskCandidate) -> bool:
    """Return whether two known dates, times, or deadlines differ."""
    for field in _DATE_TIME_FIELDS:
        current = getattr(candidate, field)
        prior = getattr(previous, field)
        if current is not None and prior is not None:
            if _value_for_comparison(current) != _value_for_comparison(prior):
                return True
    return False


def _has_same_date_or_time(
    candidate: TaskCandidate, previous: TaskCandidate
) -> bool:
    """Return whether at least one known date, time, or deadline is the same."""
    for field in _DATE_TIME_FIELDS:
        current = getattr(candidate, field)
        prior = getattr(previous, field)
        if (
            current is not None
            and prior is not None
            and _value_for_comparison(current) == _value_for_comparison(prior)
        ):
            return True
    return False


def _has_different_repeat_schedule(candidate: TaskCandidate, previous: TaskCandidate) -> bool:
    """Return whether both known repeat schedules differ."""
    repeat_schedule = _clean_text(candidate.recurrence or "")
    prior_repeat_schedule = _clean_text(previous.recurrence or "")
    return bool(
        repeat_schedule
        and prior_repeat_schedule
        and repeat_schedule != prior_repeat_schedule
    )


def _has_same_repeat_schedule(candidate: TaskCandidate, previous: TaskCandidate) -> bool:
    """Return whether both repeat schedules are present and say the same thing."""
    repeat_schedule = _clean_text(candidate.recurrence or "")
    prior_repeat_schedule = _clean_text(previous.recurrence or "")
    return bool(repeat_schedule and repeat_schedule == prior_repeat_schedule)


def _has_different_task_details(candidate: TaskCandidate, previous: TaskCandidate) -> bool:
    """Return whether known type, course, or location values differ."""
    for field in _TASK_DETAIL_FIELDS:
        current = _value_for_comparison(getattr(candidate, field))
        prior = _value_for_comparison(getattr(previous, field))
        if current is not None and prior is not None and current != prior:
            return True
    return False


def _has_similar_title_and_description(
    candidate: TaskCandidate, previous: TaskCandidate
) -> bool:
    """Return whether the titles and available descriptions are similar enough."""
    title = _clean_text(candidate.title)
    prior_title = _clean_text(previous.title)
    # The titles must meet the configured similarity threshold.
    if SequenceMatcher(None, title, prior_title).ratio() < TEXT_SIMILARITY_THRESHOLD:
        return False
    description = _clean_text(candidate.description or "")
    prior_description = _clean_text(previous.description or "")
    # A missing description is okay; compare descriptions only when both are present.
    return not description or not prior_description or SequenceMatcher(
        None, description, prior_description
    ).ratio() >= TEXT_SIMILARITY_THRESHOLD


def _is_duplicate(candidate: TaskCandidate, previous: TaskCandidate) -> bool:
    # Different known dates, times, or deadlines mean these are different tasks.
    if _has_different_date_or_time(candidate, previous):
        return False
    # Different known repeat schedules also mean these are different tasks.
    if _has_different_repeat_schedule(candidate, previous):
        return False
    # At least one date, time, deadline, or matching repeat schedule must be known.
    if not (
        _has_same_date_or_time(candidate, previous)
        or _has_same_repeat_schedule(candidate, previous)
    ):
        return False
    # Different known type, course, or location details keep both tasks.
    if _has_different_task_details(candidate, previous):
        return False
    # Finally, the title must match closely; compare descriptions when both exist.
    return _has_similar_title_and_description(candidate, previous)


def deduplicate_task_candidates(
    candidates: Sequence[TaskCandidate],
    retained_candidates: Sequence[TaskCandidate] = (),
) -> tuple[TaskCandidate, ...]:
    """Return new candidates not duplicated by retained or earlier new candidates."""

    # Compare each new candidate with both prior retained values and earlier values
    # accepted from this sequence; only return values introduced by this call.
    values = (candidates, retained_candidates)
    if any(
        isinstance(value, (str, bytes)) or not isinstance(value, Sequence)
        for value in values
    ):
        raise CandidateDeduplicationError(
            "candidates must be a sequence of TaskCandidate values"
        )
    for value in values:
        if any(not isinstance(candidate, TaskCandidate) for candidate in value):
            raise CandidateDeduplicationError(
                "candidates must be a sequence of TaskCandidate values"
            )
    prior = list(retained_candidates)
    new_retained: list[TaskCandidate] = []
    for candidate in candidates:
        if any(
            _is_duplicate(candidate, previous)
            for previous in (*prior, *new_retained)
        ):
            continue
        new_retained.append(candidate)
    return tuple(new_retained)
