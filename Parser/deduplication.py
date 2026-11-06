"""Deduplication recommendations, kept internal to data processing."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Sequence

from .models import TaskCandidate


class DedupAction(str, Enum):
    INSERT = "insert"
    MERGE = "merge"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class DeduplicationResult:
    """A non-mutating recommendation for a candidate and existing candidates."""

    action: DedupAction
    candidate: TaskCandidate
    matched_candidate: TaskCandidate | None = None
    score: float | None = None
    reason: str | None = None
    proposed_merged_candidate: TaskCandidate | None = None


class DuplicateChecker(Protocol):
    def check(
        self,
        candidate: TaskCandidate,
        candidates: Sequence[TaskCandidate],
    ) -> DeduplicationResult: ...
