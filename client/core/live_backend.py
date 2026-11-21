from __future__ import annotations

import asyncio
from typing import Any

from requests import HTTPError

from client.core.backend import AuthenticationError, ClientBackend, RegistrationError
from client.core.models import ClientUser, ConnectionStatus, SyncResult
from client.core.source_preferences import ALL_SOURCE_NAMES


def _source_platform(task: Any) -> str | None:
    if isinstance(task, dict):
        return task.get("source_platform")
    return getattr(task, "source_platform", None)


class LiveBackend(ClientBackend):
    """Thin adapter over the crawler branch's current Database facade."""

    def __init__(self) -> None:
        self._users: dict[str, Any] = {}
        self._access_tokens: dict[str, str] = {}
        self._crawl_locks: dict[str, asyncio.Lock] = {}
        # TODO(backend-integration): replace this process-local fallback with
        # persisted per-user source preferences exposed by the backend API/DB.
        # Page and controller code should not need to change when that arrives.
        self._disabled_sources: dict[str, set[str]] = {}

    async def login(self, username: str, password: str) -> ClientUser:
        from Database.auth import sign_in

        try:
            access_token, backend_user = await asyncio.to_thread(
                sign_in, username.strip(), password
            )
        except (HTTPError, ValueError) as exc:
            raise AuthenticationError("Incorrect email or password") from exc
        if backend_user is None or backend_user.id is None:
            raise AuthenticationError("Incorrect email or password")

        user = ClientUser(
            id=str(backend_user.id),
            username=backend_user.username or username.strip(),
            portal_status=backend_user.portal_status,
            moodle_status=backend_user.moodle_status,
        )
        self._users[user.id] = backend_user
        self._access_tokens[user.id] = access_token
        return user

    async def register(self, username: str, password: str) -> ClientUser:
        from Database.auth import sign_up

        clean_username = username.strip()
        try:
            access_token, backend_user = await asyncio.to_thread(
                sign_up,
                clean_username,
                password,
            )
        except HTTPError as exc:
            if exc.response is not None and exc.response.status_code in {400, 409, 422}:
                raise RegistrationError("This email is already registered or invalid.") from exc
            raise RegistrationError("Could not create the account.") from exc
        except (TypeError, ValueError) as exc:
            raise RegistrationError(str(exc)) from exc

        if backend_user.id is None:
            raise RegistrationError("The account was not created.")
        user = ClientUser(
            id=str(backend_user.id),
            username=backend_user.username or clean_username,
            portal_status=backend_user.portal_status,
            moodle_status=backend_user.moodle_status,
        )
        self._users[user.id] = backend_user
        self._access_tokens[user.id] = access_token
        return user

    async def change_password(
        self, user: ClientUser, current_password: str, new_password: str
    ) -> SyncResult:
        from Database.auth import sign_in
        from client.core.account_auth import update_password

        try:
            access_token, verified_user = await asyncio.to_thread(
                sign_in, user.username, current_password
            )
            if verified_user is None or str(verified_user.id) != user.id:
                return SyncResult(ok=False, message="Current password is incorrect")
            await asyncio.to_thread(update_password, access_token, new_password)
        except (HTTPError, TypeError, ValueError):
            return SyncResult(ok=False, message="Could not change the password")

        self._users[user.id] = verified_user
        self._access_tokens[user.id] = access_token
        return SyncResult(ok=True, message="Password changed")

    async def get_tasks(self, user: ClientUser) -> list[Any]:
        from Database.Repository.task_repository import TaskRepository
        from Database.Repository.user_task_repository import UserTaskRepository

        public_tasks = await asyncio.to_thread(TaskRepository().get_tasks, 1000)
        access_token = self._access_tokens.get(user.id)
        if access_token is None:
            tasks = public_tasks
        else:
            personal_tasks = await asyncio.to_thread(
                UserTaskRepository(
                    access_token=access_token,
                    user_id=user.id,
                ).get_tasks,
                1000,
            )
            tasks = [*public_tasks, *personal_tasks]
        disabled = await self.get_disabled_sources(user)
        return [task for task in tasks if _source_platform(task) not in disabled]

    async def get_connection_status(self, user: ClientUser) -> ConnectionStatus:
        backend_user = self._users.get(user.id)
        if backend_user is None:
            return ConnectionStatus(
                portal=user.portal_status,
                moodle=user.moodle_status,
            )
        return ConnectionStatus(
            portal=backend_user.portal_status,
            moodle=backend_user.moodle_status,
            portal_configured=bool(
                backend_user.portal_username and backend_user.portal_password
            ),
            moodle_configured=bool(backend_user.moodle_session),
        )

    async def save_portal_credentials(
        self, user: ClientUser, portal_username: str, portal_password: str
    ) -> SyncResult:
        from Database.Repository.user_repository import UserRepository

        if not portal_username.strip() or not portal_password:
            return SyncResult(ok=False, message="Enter your Portal ID and password")
        access_token = self._access_tokens.get(user.id)
        if access_token is None:
            return SyncResult(ok=False, message="Sign in again before connecting Portal")

        try:
            updated_user = await asyncio.to_thread(
                UserRepository(access_token=access_token).update_user,
                user.id,
                {
                    "portal_username": portal_username.strip(),
                    "portal_password": portal_password,
                },
            )
        except (HTTPError, TypeError, ValueError):
            return SyncResult(ok=False, message="Could not save Portal credentials")

        self._users[user.id] = updated_user
        return SyncResult(ok=True, message="Portal credentials saved")

    async def get_disabled_sources(self, user: ClientUser) -> set[str]:
        return set(self._disabled_sources.get(user.id, set()))

    async def set_source_enabled(
        self, user: ClientUser, source_name: str, enabled: bool
    ) -> None:
        disabled = self._disabled_sources.setdefault(user.id, set())
        if enabled:
            disabled.discard(source_name)
        elif source_name in ALL_SOURCE_NAMES:
            disabled.add(source_name)

    async def set_all_sources_enabled(
        self, user: ClientUser, enabled: bool
    ) -> None:
        self._disabled_sources[user.id] = set() if enabled else set(ALL_SOURCE_NAMES)

    async def sync(self, user: ClientUser, scope: str = "all") -> SyncResult:
        from client.core.personal_crawl import run_personal_crawl

        backend_user = self._users.get(user.id)
        access_token = self._access_tokens.get(user.id)
        if backend_user is None or access_token is None:
            return SyncResult(ok=False, message="Sign in again before refreshing")
        if not (
            backend_user.portal_username
            or backend_user.portal_session
            or backend_user.moodle_session
        ):
            return SyncResult(
                ok=False,
                message="Connect Portal or Moodle before running a personal crawl",
            )

        disabled_sources = await self.get_disabled_sources(user)
        enabled_personal_sources = {"Portal", "Moodle"} - disabled_sources
        if not enabled_personal_sources:
            return SyncResult(
                ok=False,
                message="Enable Portal or Moodle before running a personal crawl",
            )
        portal_ready = (
            "Portal" in enabled_personal_sources
            and backend_user.portal_username
            and backend_user.portal_password
            and backend_user.portal_session
        )
        moodle_ready = (
            "Moodle" in enabled_personal_sources
            and backend_user.moodle_session
        )
        if not (portal_ready or moodle_ready):
            return SyncResult(
                ok=False,
                message="Your personal crawler session is not ready yet",
            )

        lock = self._crawl_locks.setdefault(user.id, asyncio.Lock())
        if lock.locked():
            return SyncResult(ok=False, message="Your personal crawl is already running")

        async with lock:
            try:
                new_count, total_count = await asyncio.to_thread(
                    run_personal_crawl,
                    backend_user,
                    access_token,
                    enabled_personal_sources,
                )
            except Exception:
                return SyncResult(ok=False, message="Personal crawl failed")

        return SyncResult(
            ok=True,
            message=(
                f"Personal calendar refreshed: {new_count} new, "
                f"{total_count} stored"
            ),
        )

