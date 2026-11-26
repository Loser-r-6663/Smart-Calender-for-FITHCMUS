from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Any

from requests import HTTPError, RequestException

from client.core.backend import AuthenticationError, ClientBackend, RegistrationError, SessionExpiredError, bridge_task_load
from client.core.models import (
    ClientUser,
    ConnectionStatus,
    ScheduleViewData,
    SyncResult,
    TaskDraft,
)
from client.core.schedule_service import (
    apply_draft_to_task,
    build_schedule_view_data,
    normalize_drl,
)
from client.core.source_preferences import ALL_SOURCE_NAMES


logger = logging.getLogger(__name__)


def _source_platform(task: Any) -> str | None:
    if isinstance(task, dict):
        return task.get("source_platform")
    return getattr(task, "source_platform", None)


def _has_id_and_type(task: Any) -> bool:
    if isinstance(task, dict):
        return bool(task.get("id")) and "type" in task
    return bool(getattr(task, "id", None)) and hasattr(task, "type")


class LiveBackend(ClientBackend):
    """Adapter over Supabase repositories (`tasks`, `user_task`, `user_task_state`)."""

    def __init__(self) -> None:
        self._original_groups = {}
        self._users: dict[str, Any] = {}
        self._access_tokens: dict[str, str] = {}
        self._crawl_locks: dict[str, asyncio.Lock] = {}
        self._disabled_sources: dict[str, set[str]] = {}
        self._personal_tasks_by_id: dict[str, dict[str, Any]] = {}
        self._public_tasks_by_id: dict[str, dict[str, Any]] = {}
        self._merged_tasks_by_id: dict[str, dict[str, Any]] = {}

    def _state_repository(self, user: ClientUser):
        from Database.Repository.user_task_state_repository import (
            UserTaskStateRepository,
        )

        access_token = self._access_tokens.get(user.id)
        if access_token is None:
            return None
        return UserTaskStateRepository(
            access_token=access_token,
            user_id=user.id,
        )

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
        tasks, _, _ = await self._read_tasks(user)
        return tasks

    async def _read_tasks(self, user: ClientUser):
        from DataProcessor.Standardization.Task import Task
        from Database.Repository.task_repository import TaskRepository
        from Database.Repository.user_task_repository import UserTaskRepository

        access_token = self._access_tokens.get(user.id)
        if access_token is not None and (not access_token or not user.id):
            raise SessionExpiredError("Session expired. Sign in again.")
        public_tasks = list(await asyncio.to_thread(TaskRepository().get_tasks, None))
        if access_token is None:
            personal_tasks: list[Any] = []
        else:
            personal_tasks = list(
                await asyncio.to_thread(
                    UserTaskRepository(
                        access_token=access_token,
                        user_id=user.id,
                    ).get_tasks,
                    None,
                )
            )

        if self._access_tokens.get(user.id) != access_token:
            raise SessionExpiredError("Session changed. Sign in again.")
        groups = (("public", public_tasks), ("personal", personal_tasks))
        seen = set()
        for scope, originals in groups:
            for original in originals:
                task_id = original.get("id") if isinstance(original, dict) else getattr(original, "id", None)
                if task_id is not None:
                    if task_id in seen:
                        raise ValueError("Task UUIDs must be unique across public and personal originals")
                    seen.add(task_id)
                owner = original.get("user_id") if isinstance(original, dict) else getattr(original, "user_id", None)
                if scope == "personal" and owner not in (None, user.id):
                    raise ValueError("Personal task belongs to another owner")
        raw_combined = public_tasks + personal_tasks
        if not raw_combined or not all(_has_id_and_type(t) for t in raw_combined):
            disabled = await self.get_disabled_sources(user)
            return [task for task in raw_combined if _source_platform(task) not in disabled], groups, disabled

        public_by_id = {
            str(getattr(t, "id", None) or t["id"]): t for t in public_tasks
        }
        personal_by_id = {
            str(getattr(t, "id", None) or t["id"]): t for t in personal_tasks
        }

        state_repo = self._state_repository(user)
        states: dict[str, dict[str, Any]] = {}
        if state_repo is not None:
            try:
                states = await asyncio.to_thread(
                    state_repo.get_task_states,
                    raw_combined,
                )
            except (HTTPError, RequestException, ValueError) as error:
                if isinstance(error, HTTPError) and error.response is not None and error.response.status_code in (401, 403):
                    raise
                logger.warning("Could not load user_task_state for %s", user.id)

        disabled = await self.get_disabled_sources(user)
        if self._access_tokens.get(user.id) != access_token:
            raise SessionExpiredError("Session changed. Sign in again.")
        merged: list[Task] = []
        merged_map: dict[str, Task] = {}
        for rec in raw_combined:
            task = Task.from_any(rec)
            if task.id and task.id in states:
                task = Task.model_validate({**task.model_dump(), **states[task.id]})
            if task.id:
                merged_map[task.id] = task
            if (task.source_platform or "Custom") not in disabled:
                merged.append(task)

        self._original_groups[user.id] = groups
        self._public_tasks_by_id[user.id] = public_by_id
        self._personal_tasks_by_id[user.id] = personal_by_id
        self._merged_tasks_by_id[user.id] = merged_map
        return merged, groups, disabled

    async def create_task(self, user: ClientUser, task: TaskDraft) -> SyncResult:
        return await self._save_custom_task(user, task)

    async def _persist_schedule_flags(
        self,
        user: ClientUser,
        task_id: str,
        draft: TaskDraft,
        *,
        status: str = "proposed",
    ) -> None:
        state_repo = self._state_repository(user)
        if state_repo is None or not task_id:
            return
        local_task = apply_draft_to_task(draft, None, task_id=task_id)
        local_task.status = status  # type: ignore[assignment]
        try:
            await asyncio.to_thread(state_repo.update_tasks, [local_task])
        except (HTTPError, RequestException, ValueError):
            logger.debug("Skipped user_task_state upsert for %s", task_id)

    async def update_task(
        self, user: ClientUser, task_id: str, task: TaskDraft
    ) -> SyncResult:
        from pydantic import ValidationError

        repository = self._custom_task_repository(user)
        if repository is None:
            return SyncResult(ok=False, message="Sign in again before editing tasks")

        personal_map = self._personal_tasks_by_id.get(user.id, {})
        public_map = self._public_tasks_by_id.get(user.id, {})
        existing_merged = self._merged_tasks_by_id.get(user.id, {}).get(task_id)
        kept_status = (
            "rejected"
            if existing_merged and existing_merged.status == "rejected"
            else "proposed"
        )

        # Case 1: Editing a personal crawled or null-source task in user_task
        if task_id in personal_map and _source_platform(personal_map[task_id]) != "Custom":
            orig_source = _source_platform(personal_map[task_id])
            try:
                extracted = self._task_model(
                    user, task, source_platform=orig_source, strict_db=True
                )
                updated = await asyncio.to_thread(
                    repository.update_owned_task,
                    task_id,
                    extracted,
                )
            except (RequestException, TypeError, ValidationError, ValueError):
                logger.exception("Could not update personal task %s for %s", task_id, user.id)
                return SyncResult(
                    ok=False,
                    message="Could not update the task. Check the fields and try again.",
                )
            if not updated:
                return SyncResult(ok=False, message="Task was not found")
            await self._persist_schedule_flags(user, task_id, task, status=kept_status)
            return SyncResult(ok=True, message="Task updated")

        # Case 2: Editing/completing info on a shared public task -> create personal override & hide original
        if task_id in public_map and task_id not in personal_map:
            orig_pub = public_map[task_id]
            orig_source = _source_platform(orig_pub)
            try:
                override_extracted = self._task_model(
                    user, task, source_platform=orig_source, strict_db=True
                )
                response = await asyncio.to_thread(
                    repository.save_tasks, [override_extracted]
                )
                created_id = self._extract_created_id(response)
                if created_id:
                    await self._persist_schedule_flags(
                        user, created_id, task, status=kept_status
                    )
                await self.set_task_schedule_state(user, task_id, status="rejected")
                return SyncResult(ok=True, message="Task updated")
            except (RequestException, TypeError, ValidationError, ValueError):
                logger.exception("Could not save override for public task %s", task_id)
                return SyncResult(
                    ok=False,
                    message="Could not save task changes. Check the fields and try again.",
                )

        # Case 3: Custom task (or direct uncached task_id)
        try:
            extracted_task = self._task_model(user, task)
            try:
                updated = await asyncio.to_thread(
                    repository.update_custom_task,
                    task_id,
                    extracted_task,
                )
            except HTTPError:
                fallback_task = self._task_model(
                    user, task, source_platform=None, strict_db=True
                )
                updated = await asyncio.to_thread(
                    repository.update_owned_task,
                    task_id,
                    fallback_task,
                )
        except (RequestException, TypeError, ValidationError, ValueError):
            logger.exception("Could not update custom task for user %s", user.id)
            return SyncResult(
                ok=False,
                message="Could not update the task. Check the service and try again.",
            )

        if not updated:
            return SyncResult(ok=False, message="Custom task was not found")

        await self._persist_schedule_flags(user, task_id, task, status=kept_status)
        return SyncResult(ok=True, message="Task updated")

    async def delete_task(self, user: ClientUser, task_id: str) -> SyncResult:
        repository = self._custom_task_repository(user)
        if repository is None:
            return SyncResult(ok=False, message="Sign in again before deleting tasks")

        personal_map = self._personal_tasks_by_id.get(user.id, {})
        public_map = self._public_tasks_by_id.get(user.id, {})
        state_repo = self._state_repository(user)

        if task_id in personal_map and _source_platform(personal_map[task_id]) != "Custom":
            try:
                deleted = await asyncio.to_thread(
                    repository.delete_owned_task,
                    task_id,
                )
                if state_repo is not None:
                    await asyncio.to_thread(state_repo.delete_task_states, [task_id])
            except (RequestException, TypeError, ValueError):
                logger.exception("Could not delete personal task %s", task_id)
                return SyncResult(
                    ok=False,
                    message="Could not delete the task. Check the service and try again.",
                )
            if not deleted:
                return SyncResult(ok=False, message="Task was not found")
            return SyncResult(ok=True, message="Task deleted")

        if task_id in public_map and task_id not in personal_map:
            return await self.set_task_schedule_state(user, task_id, status="rejected")

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

        if state_repo is not None and task_id in personal_map:
            try:
                await asyncio.to_thread(state_repo.delete_task_states, [task_id])
            except (HTTPError, RequestException, ValueError):
                pass
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
    def _extract_created_id(response: Any) -> str | None:
        if response is not None and hasattr(response, "json"):
            rows = response.json()
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                return str(rows[0].get("id") or "") or None
        return None

    @staticmethod
    def _task_model(
        user: ClientUser,
        task: TaskDraft,
        *,
        source_platform: str | None = "Custom",
        strict_db: bool = False,
    ) -> Any:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from DataProcessor.Standardization.BaseTask import DateDayTime, Location
        from DataProcessor.Standardization.ExtractedTask import ExtractedTask

        tz = ZoneInfo("Asia/Ho_Chi_Minh")
        kind = task.kind
        points = task.training_points
        est_hours = task.estimated_hours

        if strict_db and kind == "event":
            # Ensure compatibility with strict user_task event constraints on Supabase
            if points is None and source_platform is None:
                kind = "personal"
            else:
                if points is None:
                    points = 0
                if est_hours is None or est_hours <= 0:
                    if task.start_time and task.end_time and task.end_time > task.start_time:
                        delta_mins = (
                            task.end_time.hour * 60 + task.end_time.minute
                        ) - (task.start_time.hour * 60 + task.start_time.minute)
                        est_hours = max(0.5, round(delta_mins / 60.0, 2))
                    else:
                        est_hours = 1.0

        if task.recurrence and task.weekday:
            start_dt = DateDayTime(day=task.weekday, time=task.start_time)
            end_dt = (
                DateDayTime(day=task.weekday, time=task.end_time)
                if task.end_time
                else None
            )
        else:
            start_dt = (
                DateDayTime(date=task.scheduled_date, time=task.start_time)
                if task.scheduled_date
                else None
            )
            end_dt = (
                DateDayTime(date=task.scheduled_date, time=task.end_time)
                if task.scheduled_date and task.end_time
                else None
            )

        loc = (
            Location(room=task.location, campus=task.campus)
            if (task.location or task.campus)
            else None
        )
        return ExtractedTask(
            user_id=user.id,
            title=task.title,
            type=kind,
            start_time=start_dt,
            end_time=end_dt,
            deadline=task.deadline,
            course=task.course,
            location=loc,
            description=task.description,
            estimated_hours=est_hours,
            training_points=points,
            training_point_category=(
                None if points == 0 else task.training_point_category
            ),
            source_url=task.source_url or "",
            source_platform=source_platform,  # type: ignore[arg-type]
            updated_at=datetime.now(tz),
        )

    async def _save_custom_task(self, user: ClientUser, task: TaskDraft) -> SyncResult:
        from pydantic import ValidationError
        from Database.Repository.user_task_repository import UserTaskRepository

        access_token = self._access_tokens.get(user.id)
        if access_token is None:
            return SyncResult(ok=False, message="Sign in again before creating a task")

        try:
            repository = UserTaskRepository(
                access_token=access_token,
                user_id=user.id,
            )
            extracted_task = self._task_model(user, task)
            try:
                response = await asyncio.to_thread(
                    repository.save_tasks, [extracted_task]
                )
            except HTTPError:
                fallback_task = self._task_model(
                    user, task, source_platform=None, strict_db=True
                )
                response = await asyncio.to_thread(
                    repository.save_tasks, [fallback_task]
                )

            created_id = self._extract_created_id(response)
            if created_id:
                await self._persist_schedule_flags(user, created_id, task)
        except (RequestException, TypeError, ValidationError, ValueError):
            logger.exception("Could not save custom task for user %s", user.id)
            return SyncResult(
                ok=False,
                message="Could not save the task. Check the service and try again.",
            )

        return SyncResult(ok=True, message="Task created")

    async def run_schedule(
        self, user: ClientUser, week_anchor: date | None = None
    ) -> ScheduleViewData:
        from DataProcessor.Standardization.Task import Task

        visible_tasks = await self.get_tasks(user)
        task_models = [
            Task.from_any(item)
            for item in visible_tasks
            if _has_id_and_type(item) or isinstance(item, Task)
        ]
        initial = await self.get_initial_drl(user)
        state_repo = self._state_repository(user)

        return await asyncio.to_thread(
            lambda: build_schedule_view_data(
                task_models,
                initial_drl=initial,
                database=state_repo,
                week_anchor=week_anchor,
            )
        )

    async def set_task_schedule_state(
        self,
        user: ClientUser,
        task_id: str,
        *,
        status: str | None = None,
        compulsory: bool | None = None,
    ) -> SyncResult:
        state_repo = self._state_repository(user)
        if state_repo is None:
            return SyncResult(ok=False, message="Sign in again before updating schedule")

        if user.id not in self._merged_tasks_by_id:
            await self.get_tasks(user)

        existing = self._merged_tasks_by_id.get(user.id, {}).get(task_id)
        if existing is None:
            return SyncResult(ok=False, message="Task was not found")

        updated = existing.model_copy(deep=True)
        if status is not None:
            updated.status = status  # type: ignore[assignment]
        if compulsory is not None:
            updated.compulsory = compulsory
            if compulsory and updated.status == "rejected":
                updated.status = "proposed"

        try:
            await asyncio.to_thread(state_repo.update_tasks, [updated])
            self._merged_tasks_by_id.setdefault(user.id, {})[task_id] = updated
        except (HTTPError, RequestException, ValueError):
            logger.exception("Could not update user_task_state for %s", task_id)
            return SyncResult(
                ok=False,
                message="Could not save schedule state. Make sure user_task.sql migration has been applied.",
            )

        if status == "rejected":
            return SyncResult(ok=True, message="Removed from schedule")
        if compulsory is True:
            return SyncResult(ok=True, message="Pinned to schedule")
        if status == "proposed":
            return SyncResult(ok=True, message="Restored to schedule candidates")
        return SyncResult(ok=True, message="Schedule preference updated")

    async def get_initial_drl(self, user: ClientUser) -> dict[str, int]:
        backend_user = self._users.get(user.id)
        if backend_user is None:
            return normalize_drl(None)
        return normalize_drl(getattr(backend_user, "training_points", None))

    async def save_initial_drl(
        self, user: ClientUser, points: dict[str, int]
    ) -> SyncResult:
        from Database.Repository.user_repository import UserRepository

        normalized = normalize_drl(points)
        backend_user = self._users.get(user.id)
        if backend_user is not None:
            backend_user.training_points = dict(normalized)

        access_token = self._access_tokens.get(user.id)
        if access_token is None:
            return SyncResult(ok=True, message="Training points updated for this session")

        try:
            updated_user = await asyncio.to_thread(
                UserRepository(access_token=access_token).update_user,
                user.id,
                {"training_points": normalized},
            )
            self._users[user.id] = updated_user
        except (HTTPError, RequestException, TypeError, ValueError):
            logger.warning("Could not persist training_points to Supabase for %s", user.id)
            return SyncResult(
                ok=True,
                message="Training points updated locally (run users.sql migration to persist on cloud)",
            )

        return SyncResult(ok=True, message="Training points baseline updated")

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
        from client.core.personal_crawl import PersonalCrawlError, log_crawl_failure, run_personal_crawl

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
                result = await asyncio.to_thread(
                    run_personal_crawl,
                    backend_user,
                    access_token,
                    enabled_personal_sources,
                )
            except PersonalCrawlError as error:
                return SyncResult(ok=False, message=str(error))
            except Exception as error:
                log_crawl_failure("personal", "initialization", error)
                return SyncResult(ok=False, message=(
                    "Personal crawl could not start. Check terminal diagnostics, "
                    "reconnect Portal/Moodle in Settings, then retry."
                ))

        new_count, total_count = result
        failed_sources = getattr(result, "failed_sources", ())
        if failed_sources:
            return SyncResult(ok=False, message=(
                f"Personal crawl partially completed: {new_count} new, {total_count} stored. "
                f"{', '.join(failed_sources)} failed; reconnect the source in Settings "
                "and retry. Check terminal diagnostics."
            ))

        return SyncResult(
            ok=True,
            message=(
                f"Personal calendar refreshed: {new_count} new, "
                f"{total_count} stored"
            ),
        )

    async def load_tasks(self, user):
        from Database.Repository.task_repository import TaskRepository
        if user is None:
            public = await asyncio.to_thread(TaskRepository().get_tasks, None)
            from client.core.backend import task_load
            return task_load((("public", public),), set())
        token = self._access_tokens.get(user.id)
        if not token or not user.id:
            raise SessionExpiredError("Session expired. Sign in again.")
        try:
            tasks, groups, disabled = await self._read_tasks(user)
        except HTTPError as error:
            if error.response is not None and error.response.status_code in (401, 403):
                raise SessionExpiredError("Session expired. Sign in again.") from error
            raise
        if self._access_tokens.get(user.id) != token:
            raise SessionExpiredError("Session changed. Sign in again.")
        return bridge_task_load(groups, tasks, disabled)

    def logout(self, user):
        super().logout(user)
        self._users.pop(user.id, None)
        self._access_tokens.pop(user.id, None)
        for cache in (self._original_groups, self._personal_tasks_by_id,
                      self._public_tasks_by_id, self._merged_tasks_by_id):
            cache.pop(user.id, None)
