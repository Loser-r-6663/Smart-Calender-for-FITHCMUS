"""Validation result values and the validation boundary."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .models import TaskCandidate


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: ValidationSeverity
    code: str
    message: str
    field: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Checked candidate plus structured issues; validity is derived."""

    candidate: TaskCandidate
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def valid(self) -> bool:
        return not any(issue.severity is ValidationSeverity.ERROR for issue in self.issues)


class Validator(Protocol):
    def validate(self, candidate: TaskCandidate) -> ValidationResult: ...
