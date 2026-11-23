"""Load a scoped Search snapshot using the current authenticated session."""

from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from .records import Scope, SearchRecord, map_task


class SearchLoadError(RuntimeError):
    """A repository read or record conversion failed."""


class SearchAuthenticationError(SearchLoadError):
    """Session credentials are incomplete, invalid, or rejected."""


@dataclass(frozen=True)
class SearchSnapshot:
    records: tuple[SearchRecord, ...]
    loaded_scopes: tuple[Scope, ...]
    row_limit: int

    @property
    def row_limits(self):
        return MappingProxyType({scope: self.row_limit for scope in self.loaded_scopes})

    def get_task(self, key: tuple[Scope, str]) -> SearchRecord | None:
        """Resolve details solely from this snapshot's full scoped key."""
        return next((record for record in self.records if record.key == key), None)


def load_snapshot(
    *,
    supabase_url: str,
    public_key: str,
    access_token: str | None = None,
    user_id: str | None = None,
    limit: int = 100,
) -> SearchSnapshot:
    """Load public tasks and, with a token and authenticated user.id, personal tasks.

    Supply the public client key and the session pair returned by authentication.
    Each call produces a new snapshot for that session.
    """
    if not isinstance(supabase_url, str) or not supabase_url.strip():
        raise ValueError("An explicit Supabase URL is required")
    if not isinstance(public_key, str) or not public_key.strip():
        raise ValueError("An explicit Supabase public client key is required")
    if type(limit) is not int or limit <= 0:
        raise ValueError("limit must be a positive integer")
    signed_in = access_token is not None or user_id is not None
    if signed_in:
        if (not isinstance(access_token, str) or not access_token.strip()
                or not isinstance(user_id, str) or not user_id.strip()):
            raise SearchAuthenticationError("Both an access token and authenticated user UUID are required")
        try:
            UUID(user_id)
        except ValueError as error:
            raise SearchAuthenticationError("An authenticated user UUID is required") from error

    from Database.Repository.task_repository import TaskRepository
    from Database.Repository.user_task_repository import UserTaskRepository

    records = _read(
        TaskRepository, "public", limit,
        supabase_url=supabase_url, supabase_key=public_key,
    )
    scopes: tuple[Scope, ...] = ("public",)
    if signed_in:
        records += _read(
            UserTaskRepository, "personal", limit,
            supabase_url=supabase_url, supabase_key=public_key,
            access_token=access_token, user_id=user_id,
        )
        scopes += ("personal",)
    return SearchSnapshot(records, scopes, limit)


def _read(repository_class, scope, limit, **settings):
    import requests

    try:
        tasks = repository_class(**settings).get_tasks(limit=limit)
        return tuple(map_task(task, scope=scope) for task in tasks)
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code in (401, 403):
            raise SearchAuthenticationError(f"{scope} task credentials were rejected") from error
        raise SearchLoadError(f"Could not load {scope} tasks") from error
    except Exception as error:
        raise SearchLoadError(f"Could not load {scope} tasks") from error
