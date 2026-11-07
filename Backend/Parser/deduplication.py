"""Raw fingerprint and parsed task-candidate deduplication primitives."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from difflib import SequenceMatcher
import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .errors import ParserError
from .models import RawCrawlerInput, TaskCandidate


class RawDeduplicationError(ParserError):
    """Raised when raw input cannot be safely fingerprinted."""


class CandidateDeduplicationError(ParserError):
    """Raised when parsed task candidates cannot be safely deduplicated."""


class RawDedupAction(str, Enum):
    PROCESS = "process"
    SKIP = "skip"


class RawDedupReason(str, Enum):
    NEW_RECORD = "new_record"
    DUPLICATE_CONTENT = "duplicate_content"
    UNCHANGED_URL = "unchanged_url"
    CHANGED_URL_CONTENT = "changed_url_content"


@dataclass(frozen=True, slots=True)
class RawFingerprint:
    canonical_url: str | None
    content_hash: str


@dataclass(frozen=True, slots=True)
class RawDeduplicationResult:
    action: RawDedupAction
    reason: RawDedupReason
    fingerprint: RawFingerprint
    matched_fingerprint: RawFingerprint | None = None


class RawFingerprintStore(Protocol):
    def find_by_url(self, canonical_url: str) -> RawFingerprint | None: ...

    def find_by_content_hash(self, content_hash: str) -> RawFingerprint | None: ...

    def remember(self, fingerprint: RawFingerprint) -> None: ...


class InMemoryRawFingerprintStore:
    """Process-local storage for successful raw fingerprints."""

    def __init__(self) -> None:
        # This store intentionally covers one process run, not durable deduplication so this might be changed later if we need to document the fingerprints.
        self._by_url: dict[str, RawFingerprint] = {}
        self._by_content_hash: dict[str, RawFingerprint] = {}

    def find_by_url(self, canonical_url: str) -> RawFingerprint | None:
        return self._by_url.get(canonical_url)

    def find_by_content_hash(self, content_hash: str) -> RawFingerprint | None:
        return self._by_content_hash.get(content_hash)

    def remember(self, fingerprint: RawFingerprint) -> None:
        # Preserve the first content representative while allowing URL updates.
        if fingerprint.canonical_url is not None:
            self._by_url[fingerprint.canonical_url] = fingerprint
        self._by_content_hash.setdefault(fingerprint.content_hash, fingerprint)


class RawDuplicateChecker:
    def __init__(self, store: RawFingerprintStore) -> None:
        self._store = store

    def check(self, raw: RawCrawlerInput) -> RawDeduplicationResult:
        fingerprint = fingerprint_raw_input(raw)
        # URL identity is checked first so a changed page at a known URL is processed.
        url_match = (
            self._store.find_by_url(fingerprint.canonical_url)
            if fingerprint.canonical_url is not None
            else None
        )
        if url_match is not None:
            unchanged = url_match.content_hash == fingerprint.content_hash
            reason = (
                RawDedupReason.UNCHANGED_URL
                if unchanged
                else RawDedupReason.CHANGED_URL_CONTENT
            )
            return RawDeduplicationResult(
                RawDedupAction.SKIP if unchanged else RawDedupAction.PROCESS,
                reason,
                fingerprint,
                url_match,
            )

        # A matching hash at another URL is the exact normalized duplicate case.
        content_match = self._store.find_by_content_hash(fingerprint.content_hash)
        if content_match is not None:
            return RawDeduplicationResult(
                RawDedupAction.SKIP,
                RawDedupReason.DUPLICATE_CONTENT,
                fingerprint,
                content_match,
            )
        return RawDeduplicationResult(
            RawDedupAction.PROCESS,
            RawDedupReason.NEW_RECORD,
            fingerprint,
        )

    def remember(self, fingerprint: RawFingerprint) -> None:
        self._store.remember(fingerprint)


_WHITESPACE = re.compile(r"\s+")


def _normalize_string(value: str) -> str:
    # NFKC, collapsed whitespace, and casefold remove representational text noise.
    normalized = unicodedata.normalize("NFKC", value)
    return _WHITESPACE.sub(" ", normalized).strip().casefold()


def _candidate_identity(candidate: TaskCandidate) -> tuple[object, ...]:
    temporal = tuple(
        getattr(candidate, field).isoformat() if getattr(candidate, field) else None
        for field in (
            "registration_start", "registration_end", "start_time",
            "end_time", "deadline",
        )
    )
    source_url = candidate.source_url
    if source_url is not None:
        try:
            source_url = canonicalize_url(source_url)
        except RawDeduplicationError as exc:
            raise CandidateDeduplicationError(
                "candidate source URL is not canonicalizable"
            ) from exc
    return (
        candidate.type.value,
        _normalize_string(candidate.course_code or ""),
        temporal,
        _normalize_string(candidate.recurrence or ""),
        _normalize_string(candidate.location or ""),
        candidate.source_platform.value,
        source_url,
    )


def deduplicate_task_candidates(
    candidates: Sequence[TaskCandidate],
) -> tuple[TaskCandidate, ...]:
    """Keep the first candidate from each conservative structural title group."""
    # Candidate deduplication after AI parses: prevents one response from producing duplicate or near-duplicate tasks.
    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        raise CandidateDeduplicationError(
            "candidates must be a sequence of TaskCandidate values"
        )
    retained: list[TaskCandidate] = []
    identities: list[tuple[object, ...]] = []
    titles: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, TaskCandidate):
            raise CandidateDeduplicationError(
                "candidates must be a sequence of TaskCandidate values"
            )
        identity = _candidate_identity(candidate)
        title = _normalize_string(candidate.title)
        if any(
            identity == previous_identity
            and (
                title == previous_title
                or SequenceMatcher(None, title, previous_title).ratio() >= 0.90
            )
            for previous_identity, previous_title in zip(identities, titles)
        ):
            continue
        retained.append(candidate)
        identities.append(identity)
        titles.append(title)
    return tuple(retained)


def canonicalize_url(url: str) -> str:
    if not isinstance(url, str):
        raise RawDeduplicationError("source URL must be a string")
    value = url.strip()
    if not value or any(char.isspace() for char in value):
        raise RawDeduplicationError("source URL must be a usable absolute URL")
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise RawDeduplicationError("source URL is malformed") from exc
    if not parts.scheme or not hostname:
        raise RawDeduplicationError(
            "source URL must include a scheme and hostname"
        )

    host = hostname.casefold()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    userinfo = ""
    if parts.username is not None:
        userinfo = parts.username
        if parts.password is not None:
            userinfo += f":{parts.password}"
        userinfo += "@"
    netloc = f"{userinfo}{host}"
    default_port = (parts.scheme.casefold() == "http" and port == 80) or (
        parts.scheme.casefold() == "https" and port == 443
    )
    if port is not None and not default_port:
        netloc += f":{port}"

    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    query_pairs = [
        # Tracking parameters do not identify the underlying source content.
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not (
            key.casefold().startswith("utm_")
            or key.casefold() in {"fbclid", "gclid", "ref"}
        )
    ]
    query = urlencode(sorted(query_pairs, key=lambda pair: (pair[0], pair[1])))
    return urlunsplit((parts.scheme.casefold(), netloc, path, query, ""))


def _normalize_json(value: Any, *, top_level_record: bool = False) -> Any:
    if isinstance(value, str):
        return _normalize_string(value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RawDeduplicationError("JSON numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise RawDeduplicationError("JSON mappings must use string keys")
        normalized = {}
        for key, item in value.items():
            # Link fields are envelope identity, not the record's content identity.
            if top_level_record and key in {"Link", "link", "source_url"}:
                continue
            normalized[_normalize_string(key)] = _normalize_json(item)
        # Sorted keys make equivalent JSON structures canonical before hashing.
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    raise RawDeduplicationError(
        f"unsupported JSON value type: {type(value).__name__}"
    )


def fingerprint_raw_input(raw: RawCrawlerInput) -> RawFingerprint:
    # Raw deduplication before AI: avoids paying to parse the same crawler record repeatedly.
    if not isinstance(raw, RawCrawlerInput):
        raise RawDeduplicationError("raw input must be a RawCrawlerInput")
    if isinstance(raw.payload, bytes):
        try:
            payload = raw.payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RawDeduplicationError("raw payload is not valid UTF-8") from exc
    elif isinstance(raw.payload, str):
        payload = raw.payload
    else:
        raise RawDeduplicationError("raw payload must be str or UTF-8 bytes")

    try:
        parsed = json.loads(
            payload,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (json.JSONDecodeError, ValueError):
        canonical_content = _normalize_string(payload)
    else:
        is_envelope = isinstance(parsed, dict) and "record" in parsed
        # Hash only the record: source/capture envelope metadata must not create duplicates.
        content = parsed["record"] if is_envelope else parsed
        canonical_content = json.dumps(
            _normalize_json(content, top_level_record=is_envelope),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    # UTF-8 plus SHA-256 yields a deterministic fingerprint, not semantic similarity.
    content_hash = hashlib.sha256(canonical_content.encode("utf-8")).hexdigest()
    canonical_url = (
        None if raw.source_url is None else canonicalize_url(raw.source_url)
    )
    return RawFingerprint(canonical_url, content_hash)
