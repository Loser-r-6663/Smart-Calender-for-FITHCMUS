"""Deterministic Vietnamese point expressions, independent of storage and SQL."""
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass

from .validation import SearchValidationError, validate_request

UNIT = r"(?:điểm rèn luyện|đrl|điểm)"
POINTS = re.compile(r"(?<!\w)(?:(?P<minimum>từ)\s+)?(?P<number>[0-9]+)\s+" + UNIT + r"(?!\w)", re.I)
EVENT = re.compile(r"(?<!\w)sự kiện(?!\w)", re.I)
NEGATION = re.compile(r"(?<!\w)(?:không|chẳng|chưa)(?!\w)", re.I)
UNSUPPORTED_PREFIX = re.compile(
    r"(?:không(?: phải)?|chẳng(?: phải)?|chưa|tối đa|tối thiểu|ít nhất|nhiều nhất|"
    r"hơn|trên|dưới|nhỏ hơn|lớn hơn|bằng|đến)\s*$", re.I)
UNSUPPORTED_SUFFIX = re.compile(r"^\s*(?:trở lên|trở xuống|đến\s+[0-9]|[-–—]\s*[0-9])", re.I)


class SearchInterpretationError(SearchValidationError):
    """Typed constraints are unsupported, ambiguous, or conflict with selections."""


@dataclass(frozen=True)
class Interpretation:
    original_query: str
    remaining_keyword: str
    inferred_filters: dict
    effective_filters: dict


@dataclass(frozen=True)
class InterpretedSearch:
    interpretation: Interpretation
    results: list[dict]


def interpret_request(request):
    """Interpret a normal Search request without mutating it or accessing storage."""
    validate_request(request)
    original = request.get("keyword", "")
    text = " ".join(unicodedata.normalize("NFC", original).split())
    matches = list(POINTS.finditer(text))
    if len(matches) > 1:
        raise SearchInterpretationError("Ambiguous query: multiple training-point expressions")
    inferred = {}
    remaining = " ".join(original.split())
    if matches:
        match = matches[0]
        before, after = text[:match.start()], text[match.end():]
        # A numeric fragment after a sign, decimal, or range is not an equality.
        if (NEGATION.search(text) or re.search(r"[0-9.,+\-–—<>=≤≥]\s*$", before)
                or UNSUPPORTED_PREFIX.search(before) or UNSUPPORTED_SUFFIX.search(after)):
            raise SearchInterpretationError("Unsupported training-point expression; use N điểm or từ N điểm")
        digits = match["number"].lstrip("0") or "0"
        try:
            number = int(digits)
        except ValueError as error:
            raise SearchValidationError("Invalid training-point integer") from error
        inferred["min_training_points"] = number
        if not match["minimum"]:
            inferred["max_training_points"] = number
        validate_request({"filters": inferred})
        # Remove spans separately so deleting points cannot create a new type phrase.
        spans = [(match.start(), match.end())]
        type_matches = list(EVENT.finditer(text))
        if type_matches:
            inferred["types"] = ["event"]
            spans.extend((item.start(), item.end()) for item in type_matches)
        for start, end in sorted(spans, reverse=True):
            text = text[:start] + " " + text[end:]
        remaining = " ".join(text.split())
    effective = deepcopy(dict(request.get("filters", {})))
    effective.setdefault("statuses", ["active"])
    for key, value in inferred.items():
        if key == "types":
            selected = effective.get(key, value)
            if "event" not in selected:
                raise SearchInterpretationError("Conflicting task types: inferred event is excluded")
            effective[key] = ["event"]
        elif key == "min_training_points":
            effective[key] = max(effective.get(key, value), value)
        else:
            effective[key] = min(effective.get(key, value), value)
    if ("min_training_points" in effective and "max_training_points" in effective
            and effective["min_training_points"] > effective["max_training_points"]):
        raise SearchInterpretationError("Conflicting training-point constraints")
    validate_request({**request, "keyword": remaining, "filters": effective})
    return Interpretation(original, remaining, inferred, effective)
