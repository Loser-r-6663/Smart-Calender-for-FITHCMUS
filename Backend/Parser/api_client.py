"""Small standard-library client for the task REST API."""

import json
import os
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import (
    DatabaseApiConflictError,
    DatabaseApiRequestError,
    DatabaseApiUnavailableError,
    DatabaseApiValidationError,
)


class DatabaseApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        opener: Any = None,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("DATABASE_API_URL", "http://127.0.0.1:8000")
        ).rstrip("/")
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.getenv("DATABASE_API_TIMEOUT_SECONDS", "10"))
        )
        self._opener = opener or urlopen

    @staticmethod
    def _detail(raw: bytes | str | None) -> str:
        try:
            value = json.loads(
                raw.decode("utf-8") if isinstance(raw, bytes) else raw or ""
            )
        except (TypeError, ValueError):
            value = None
        detail = value.get("detail") if isinstance(value, dict) else None
        if detail is None:
            return "database API request failed"
        return " ".join(str(detail).split())[:300]

    def _request(self, method: str, path: str, payload: Any = None) -> Any:
        # Keep wire serialization compact and independent of caller object types.
        data = (
            None
            if payload is None
            else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        request = Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        response = None
        try:
            response = self._opener(request, timeout=self.timeout_seconds)
            raw = response.read()
            if not raw:
                return {}
            try:
                return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            except (TypeError, ValueError) as exc:
                raise DatabaseApiRequestError(
                    "database API returned invalid JSON"
                ) from exc
        except HTTPError as exc:
            # Preserve validation/conflict semantics while hiding urllib details.
            detail = self._detail(exc.read())
            if exc.code == 422:
                raise DatabaseApiValidationError(detail) from exc
            if exc.code == 409:
                raise DatabaseApiConflictError(detail) from exc
            raise DatabaseApiRequestError(detail) from exc
        except (ConnectionError, TimeoutError, socket.timeout, URLError, OSError) as exc:
            raise DatabaseApiUnavailableError("database API is unavailable") from exc
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def check_health(self) -> Any:
        try:
            result = self._request("GET", "/health")
        except DatabaseApiRequestError as exc:
            if getattr(exc.__cause__, "code", None) != 404:
                raise
            result = self._request("GET", "/openapi.json")

        unhealthy = isinstance(result, dict) and (
            result.get("healthy") is False
            or result.get("database") in {"offline", "unhealthy"}
            or result.get("status") in {"offline", "unhealthy"}
        )
        if unhealthy:
            raise DatabaseApiUnavailableError(
                "database API reports an unhealthy database"
            )
        return result

    def create_task(self, payload: dict[str, Any]) -> Any:
        return self._request("POST", "/tasks", payload)

    def get_task(self, id: str) -> Any:
        return self._request("GET", f"/tasks/{id}")

    def delete_task(self, id: str) -> Any:
        return self._request("DELETE", f"/tasks/{id}")
