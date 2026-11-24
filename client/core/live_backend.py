from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from requests import HTTPError, RequestException

from client.core.backend import AuthenticationError, ClientBackend, RegistrationError
from client.core.models import ClientUser, ConnectionStatus, SyncResult, TaskDraft
from client.core.source_preferences import ALL_SOURCE_NAMES


logger = logging.getLogger(__name__)


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

        public_tasks = await asyncio.to_thread(TaskRepository().get_tasks, None)
        access_token = self._access_tokens.get(user.id)
        if access_token is None:
            tasks = public_tasks
        else:
            personal_tasks = await asyncio.to_thread(
                UserTaskRepository(
                    access_token=access_token,
                    user_id=user.id,
                ).get_tasks,
                None,
            )
            tasks = [*public_tasks, *personal_tasks]
        disabled = await self.get_disabled_sources(user)
        return [task for task in tasks if _source_platform(task) not in disabled]

    async def create_task(self, user: ClientUser, task: TaskDraft) -> SyncResult:
        return await self._save_custom_task(user, task)

    async def update_task(
        self, user: ClientUser, task_id: str, task: TaskDraft
    ) -> SyncResult:
        from pydantic import ValidationError
        from requests import RequestException

        repository = self._custom_task_repository(user)
        if repository is None:
            return SyncResult(ok=False, message="Sign in again before editing tasks")

        try:
            extracted_task = self._task_model(user, task)
            updated = await asyncio.to_thread(
                repository.update_custom_task,
                task_id,
                extracted_task,
            )
        except (RequestException, TypeError, ValidationError, ValueError):
            logger.exception("Could not update custom task for user %s", user.id)
            return SyncResult(
                ok=False,
                message="Could not update the task. Check the service and try again.",
            )

        if not updated:
            return SyncResult(ok=False, message="Custom task was not found")
        return SyncResult(ok=True, message="Task updated")

    async def delete_task(self, user: ClientUser, task_id: str) -> SyncResult:
        from requests import RequestException

        repository = self._custom_task_repository(user)
        if repository is None:
            return SyncResult(ok=False, message="Sign in again before deleting tasks")

        try:
            deleted = await asyncio.to_thread(
                repository.delete_custom_task,
                task_id,
            )
        except (RequestException, TypeError, ValueError):
            logger.exception("Could not delete custom task for user %s", user.id)
            return SyncResult(
                ok=False,
                message="Could not delete the task. Check the service and try again.",
            )

        if not deleted:
            return SyncResult(ok=False, message="Custom task was not found")
        return SyncResult(ok=True, message="Task deleted")

    def _custom_task_repository(self, user: ClientUser) -> Any | None:
        from Database.Repository.user_task_repository import UserTaskRepository

        access_token = self._access_tokens.get(user.id)
        if access_token is None:
            return None
        return UserTaskRepository(
            access_token=access_token,
            user_id=user.id,
        )

    @staticmethod
    def _task_model(user: ClientUser, task: TaskDraft) -> Any:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from DataProcessor.Standardization.BaseTask import DateDayTime, Location
        from DataProcessor.Standardization.ExtractedTask import ExtractedTask

        tz = ZoneInfo("Asia/Ho_Chi_Minh")
        return ExtractedTask(
            user_id=user.id,
            title=task.title,
            type=task.kind,
            start_time=(
                DateDayTime(date=task.scheduled_date, time=task.start_time)
                if task.scheduled_date
                else None
            ),
            end_time=(
                DateDayTime(date=task.scheduled_date, time=task.end_time)
                if task.scheduled_date and task.end_time
                else None
            ),
            deadline=task.deadline,
            course=task.course,
            location=Location(room=task.location) if task.location else None,
            description=task.description,
            source_url=task.source_url or "",
            source_platform="Custom",
            updated_at=datetime.now(tz),
        )

    async def _save_custom_task(self, user: ClientUser, task: TaskDraft) -> SyncResult:
        from pydantic import ValidationError
        from requests import RequestException
        from Database.Repository.user_task_repository import UserTaskRepository

        access_token = self._access_tokens.get(user.id)
        if access_token is None:
            return SyncResult(ok=False, message="Sign in again before creating a task")

        try:
            extracted_task = self._task_model(user, task)
            repository = UserTaskRepository(
                access_token=access_token,
                user_id=user.id,
            )
            await asyncio.to_thread(repository.save_tasks, [extracted_task])
        except (RequestException, TypeError, ValidationError, ValueError):
            logger.exception("Could not save custom task for user %s", user.id)
            return SyncResult(
                ok=False,
                message="Could not save the task. Check the service and try again.",
            )

        return SyncResult(ok=True, message="Task created")

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

    async def connect_moodle(self, user: ClientUser) -> SyncResult:
        backend_user = self._users.get(user.id)
        access_token = self._access_tokens.get(user.id)
        if backend_user is None or access_token is None:
            return SyncResult(ok=False, message="Sign in again before connecting Moodle")
        if os.environ.get("APP_ROLE") == "SERVER":
            return SyncResult(
                ok=False,
                message="Moodle sign-in requires the app to run on your computer",
            )

        lock = self._crawl_locks.setdefault(user.id, asyncio.Lock())
        if lock.locked():
            return SyncResult(
                ok=False,
                message="A personal sign-in or crawl is already running",
            )

        from playwright.sync_api import Error as PlaywrightError

        from client.core.personal_crawl import capture_moodle_session
        from Database.Repository.user_repository import UserRepository

        async with lock:
            try:
                session = await asyncio.to_thread(
                    capture_moodle_session,
                    backend_user,
                )
            except (
                AssertionError,
                ConnectionError,
                OSError,
                PlaywrightError,
                RuntimeError,
                ValueError,
            ):
                logger.exception("Moodle sign-in failed for user %s", user.id)
                return SyncResult(
                    ok=False,
                    message=(
                        "Moodle sign-in did not complete. Finish Google sign-in "
                        "in the opened browser, then try again."
                    ),
                )

            try:
                updated_user = await asyncio.to_thread(
                    lambda: UserRepository(
                        access_token=access_token
                    ).update_user(
                        user.id,
                        {"moodle_session": session, "moodle_status": True},
                    )
                )
            except (RequestException, TypeError, ValueError):
                logger.exception("Could not save Moodle session for user %s", user.id)
                return SyncResult(
                    ok=False,
                    message="Moodle sign-in succeeded, but its session could not be saved.",
                )

        self._users[user.id] = updated_user
        return SyncResult(ok=True, message="Moodle connected")

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
                logger.exception("Personal crawl failed for user %s", user.id)
                return SyncResult(ok=False, message="Personal crawl failed")

        return SyncResult(
            ok=True,
            message=(
                f"Personal calendar refreshed: {new_count} new, "
                f"{total_count} stored"
            ),
        )

