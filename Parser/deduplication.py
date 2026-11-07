"""Exact content and canonical source-URL deduplication for raw input."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .errors import ParserError
from .models import RawCrawlerInput


class RawDeduplicationError(ParserError):
    """Raised when raw input cannot be safely fingerprinted."""


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
        self._by_url: dict[str, RawFingerprint] = {}
        self._by_content_hash: dict[str, RawFingerprint] = {}

    def find_by_url(self, canonical_url: str) -> RawFingerprint | None:
        return self._by_url.get(canonical_url)

    def find_by_content_hash(self, content_hash: str) -> RawFingerprint | None:
        return self._by_content_hash.get(content_hash)

    def remember(self, fingerprint: RawFingerprint) -> None:
        if fingerprint.canonical_url is not None:
            self._by_url[fingerprint.canonical_url] = fingerprint
        self._by_content_hash.setdefault(fingerprint.content_hash, fingerprint)


class RawDuplicateChecker:
    def __init__(self, store: RawFingerprintStore) -> None:
        self._store = store

    def check(self, raw: RawCrawlerInput) -> RawDeduplicationResult:
        fingerprint = fingerprint_raw_input(raw)
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
    normalized = unicodedata.normalize("NFKC", value)
    return _WHITESPACE.sub(" ", normalized).strip().casefold()


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
            if top_level_record and key in {"Link", "link", "source_url"}:
                continue
            normalized[_normalize_string(key)] = _normalize_json(item)
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    raise RawDeduplicationError(
        f"unsupported JSON value type: {type(value).__name__}"
    )


def fingerprint_raw_input(raw: RawCrawlerInput) -> RawFingerprint:
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
        content = parsed["record"] if is_envelope else parsed
        canonical_content = json.dumps(
            _normalize_json(content, top_level_record=is_envelope),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    content_hash = hashlib.sha256(canonical_content.encode("utf-8")).hexdigest()
    canonical_url = (
        None if raw.source_url is None else canonicalize_url(raw.source_url)
    )
    return RawFingerprint(canonical_url, content_hash)
