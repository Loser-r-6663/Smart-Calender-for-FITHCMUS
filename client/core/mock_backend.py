from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4, UUID, NAMESPACE_URL, uuid5
from DataProcessor.Standardization.ExtractedTask import ExtractedTask

from DataProcessor.Standardization.Task import Task
from client.core.backend import AuthenticationError, ClientBackend, RegistrationError, bridge_task_load
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


class MockBackend(ClientBackend):
    """Offline backend used for UI development and browser tests."""

    def __init__(self, fixture_path: Path | None = None) -> None:
        self.fixture_path = fixture_path or (
            Path(__file__).resolve().parents[1] / "fixtures" / "tasks.json"
        )
        self._uses_demo_fixture = fixture_path is None
        self._crawled_tasks: dict[str, list[dict[str, Any]]] = {}
        self._last_sync: datetime | None = None
        self._disabled_sources: dict[str, set[str]] = {}
        self._manual_tasks: dict[str, list[dict[str, Any]]] = {}
        self._task_overrides: dict[str, dict[str, dict[str, Any]]] = {}
        self._deleted_ids: dict[str, set[str]] = {}
        self._initial_drl: dict[str, dict[str, int]] = {}
        demo_user = ClientUser(
            id="demo-user",
            username="student",
            portal_status=True,
            moodle_status=True,
        )
        self._accounts: dict[str, tuple[str, ClientUser]] = {
            "student": ("demo", demo_user)
        }
        self._portal_configured: set[str] = {demo_user.id}
        self._portal_connected: set[str] = {demo_user.id}
        self._moodle_configured: set[str] = {demo_user.id}
        self._moodle_connected: set[str] = {demo_user.id}
        self._awaiting_personal_crawl: set[str] = set()

    async def login(self, username: str, password: str) -> ClientUser:
        await asyncio.sleep(0.05)
        account = self._accounts.get(username.strip().lower())
        if account is None or account[0] != password:
            raise AuthenticationError("Incorrect username or password")
        return account[1]

    async def register(self, username: str, password: str) -> ClientUser:
        clean_username = username.strip()
        key = clean_username.lower()
        if not clean_username or not password:
            raise RegistrationError("Username and password are required.")
        if key in self._accounts:
            raise RegistrationError("Username is already taken.")
        user = ClientUser(id=f"mock-{key}", username=clean_username)
        self._accounts[key] = (password, user)
        self._awaiting_personal_crawl.add(user.id)
        return user

    async def change_password(
        self, user: ClientUser, current_password: str, new_password: str
    ) -> SyncResult:
        key = user.username.strip().lower()
        account = self._accounts.get(key)
        if account is None or account[0] != current_password:
            return SyncResult(ok=False, message="Current password is incorrect")
        self._accounts[key] = (new_password, account[1])
        return SyncResult(ok=True, message="Password changed")

    def _raw_user_records(self, user: ClientUser) -> list[dict[str, Any]]:
        tasks = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        if user.id in self._awaiting_personal_crawl:
            tasks = [
                task
                for task in tasks
                if task.get("source_platform") not in {"Portal", "Moodle"}
            ]
        tasks.extend(self._crawled_tasks.get(user.id, []))
        tasks.extend(self._manual_tasks.get(user.id, []))
        tasks = [task for task in tasks if not task.get("user_id") or task["user_id"] == user.id]
        deleted = self._deleted_ids.get(user.id, set())
        overrides = self._task_overrides.get(user.id, {})
        merged: list[dict[str, Any]] = []
        for record in tasks:
            rec_id = str(record.get("id") or "")
            if rec_id in deleted:
                continue
            if rec_id in overrides:
                merged.append({**record, **overrides[rec_id]})
            else:
                merged.append(dict(record))
        return merged

    async def get_tasks(self, user: ClientUser) -> list[Any]:
        await asyncio.sleep(0.05)
        tasks = self._raw_user_records(user)
        disabled = await self.get_disabled_sources(user)
        return [task for task in tasks if task.get("source_platform") not in disabled]

    async def create_task(self, user: ClientUser, task: TaskDraft) -> SyncResult:
        await asyncio.sleep(0.05)
        self._manual_tasks.setdefault(user.id, []).append(
            self._task_to_record(user, task)
        )
        return SyncResult(ok=True, message="Task created")

    @staticmethod
    def _task_to_record(
        user: ClientUser,
        task: TaskDraft,
        task_id: str | None = None,
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        recurrence = bool(task.recurrence and task.weekday)
        if recurrence:
            start_payload: dict[str, Any] | None = {
                "day": task.weekday,
                "time": task.start_time.isoformat() if task.start_time else None,
            }
            end_payload: dict[str, Any] | None = (
                {
                    "day": task.weekday,
                    "time": task.end_time.isoformat(),
                }
                if task.end_time
                else None
            )
        else:
            start_payload = (
                {
                    "date": task.scheduled_date.isoformat(),
                    "time": task.start_time.isoformat() if task.start_time else None,
                }
                if task.scheduled_date
                else None
            )
            end_payload = (
                {
                    "date": task.scheduled_date.isoformat(),
                    "time": task.end_time.isoformat() if task.end_time else None,
                }
                if task.scheduled_date and task.end_time
                else None
            )

        location_payload: Any = None
        if task.location or task.campus:
            location_payload = {
                "room": task.location,
                "campus": task.campus,
            }

        source_platform = (
            existing.get("source_platform", "Custom") if existing else "Custom"
        )
        source_url = (
            task.source_url
            if task.source_url is not None
            else (existing.get("source_url", "") if existing else "")
        )

        return {
            "id": task_id or str(uuid4()),
            "user_id": existing.get("user_id", user.id) if existing else user.id,
            "title": task.title,
            "type": task.kind,
            "start_time": start_payload,
            "end_time": end_payload,
            "deadline": task.deadline.isoformat() if task.deadline else None,
            "course": task.course,
            "location": location_payload,
            "description": task.description,
            "source_url": source_url or "",
            "source_platform": source_platform,
            "estimated_hours": task.estimated_hours,
            "training_points": task.training_points,
            "training_point_category": (
                None if task.training_points == 0 else task.training_point_category
            ),
            "recurrence": recurrence,
            "flexible": task.flexible,
            "compulsory": task.compulsory,
            "status": (
                existing.get("status", "proposed")
                if existing and existing.get("status") == "rejected"
                else "proposed"
            ),
            "user_modified": True,
        }

    async def update_task(
        self, user: ClientUser, task_id: str, task: TaskDraft
    ) -> SyncResult:
        await asyncio.sleep(0.05)
        records = self._manual_tasks.get(user.id, [])
        for index, record in enumerate(records):
            if record["id"] == task_id:
                records[index] = self._task_to_record(user, task, task_id, record)
                return SyncResult(ok=True, message="Task updated")

        visible = {str(r.get("id")): r for r in self._raw_user_records(user)}
        if task_id in visible:
            self._task_overrides.setdefault(user.id, {})[task_id] = (
                self._task_to_record(user, task, task_id, visible[task_id])
            )
            return SyncResult(ok=True, message="Task updated")

        return SyncResult(ok=False, message="Custom task was not found")

    async def delete_task(self, user: ClientUser, task_id: str) -> SyncResult:
        await asyncio.sleep(0.05)
        records = self._manual_tasks.get(user.id, [])
        for index, record in enumerate(records):
            if record["id"] == task_id:
                del records[index]
                self._task_overrides.get(user.id, {}).pop(task_id, None)
                return SyncResult(ok=True, message="Task deleted")

        visible_ids = {str(r.get("id")) for r in self._raw_user_records(user)}
        if task_id in visible_ids:
            self._deleted_ids.setdefault(user.id, set()).add(task_id)
            self._task_overrides.get(user.id, {}).pop(task_id, None)
            return SyncResult(ok=True, message="Task deleted")

        return SyncResult(ok=False, message="Custom task was not found")

    async def run_schedule(
        self, user: ClientUser, week_anchor: date | None = None
    ) -> ScheduleViewData:
        raw_records = await self.get_tasks(user)
        task_models = [Task.from_any(rec) for rec in raw_records]
        initial = await self.get_initial_drl(user)
        view_data = build_schedule_view_data(
            task_models,
            initial_drl=initial,
            database=None,
            week_anchor=week_anchor,
        )
        overrides = self._task_overrides.setdefault(user.id, {})
        manual_ids = {r["id"] for r in self._manual_tasks.get(user.id, [])}
        for model in task_models:
            if not model.id:
                continue
            if model.id in manual_ids:
                for rec in self._manual_tasks.get(user.id, []):
                    if rec["id"] == model.id:
                        rec["status"] = model.status
            elif model.id in overrides:
                overrides[model.id]["status"] = model.status
        return view_data

    async def set_task_schedule_state(
        self,
        user: ClientUser,
        task_id: str,
        *,
        status: str | None = None,
        compulsory: bool | None = None,
    ) -> SyncResult:
        for record in self._manual_tasks.get(user.id, []):
            if record["id"] == task_id:
                if status is not None:
                    record["status"] = status
                if compulsory is not None:
                    record["compulsory"] = compulsory
                return SyncResult(ok=True, message=self._state_message(status, compulsory))

        visible = {str(r.get("id")): r for r in self._raw_user_records(user)}
        if task_id not in visible:
            return SyncResult(ok=False, message="Task was not found")

        patch = dict(self._task_overrides.setdefault(user.id, {}).get(task_id, {}))
        if status is not None:
            patch["status"] = status
        if compulsory is not None:
            patch["compulsory"] = compulsory
            if compulsory and patch.get("status") == "rejected":
                patch["status"] = "proposed"
        self._task_overrides[user.id][task_id] = patch
        return SyncResult(ok=True, message=self._state_message(status, compulsory))

    @staticmethod
    def _state_message(status: str | None, compulsory: bool | None) -> str:
        if status == "rejected":
            return "Removed from schedule"
        if compulsory is True:
            return "Pinned to schedule"
        if status == "proposed":
            return "Restored to schedule candidates"
        return "Schedule preference updated"

    async def get_initial_drl(self, user: ClientUser) -> dict[str, int]:
        return normalize_drl(self._initial_drl.get(user.id))

    async def save_initial_drl(
        self, user: ClientUser, points: dict[str, int]
    ) -> SyncResult:
        self._initial_drl[user.id] = normalize_drl(points)
        return SyncResult(ok=True, message="Training points baseline updated")

    async def get_connection_status(self, user: ClientUser) -> ConnectionStatus:
        return ConnectionStatus(
            portal=user.portal_status or user.id in self._portal_connected,
            moodle=user.moodle_status or user.id in self._moodle_connected,
            portal_configured=(
                user.portal_status or user.id in self._portal_configured
            ),
            moodle_configured=(
                user.moodle_status or user.id in self._moodle_configured
            ),
            last_sync=self._last_sync,
        )

    async def save_portal_credentials(
        self, user: ClientUser, portal_username: str, portal_password: str
    ) -> SyncResult:
        if not portal_username.strip() or not portal_password:
            return SyncResult(ok=False, message="Enter your Portal ID and password")
        self._portal_configured.add(user.id)
        return SyncResult(ok=True, message="Portal credentials saved")

    async def connect_moodle(self, user: ClientUser) -> SyncResult:
        await asyncio.sleep(0.2)
        self._moodle_configured.add(user.id)
        self._moodle_connected.add(user.id)
        return SyncResult(ok=True, message="Mock Moodle connection complete")

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
        await asyncio.sleep(0.4)
        disabled = await self.get_disabled_sources(user)
        status = await self.get_connection_status(user)
        enabled_personal_sources = {
            source
            for source, ready in {
                "Portal": status.portal_configured,
                "Moodle": status.moodle_configured,
            }.items()
            if ready and source not in disabled
        }
        if not enabled_personal_sources:
            return SyncResult(
                ok=False,
                message="Connect and enable Portal or Moodle first",
            )

        tasks = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        personal_count = sum(
            task.get("source_platform") in enabled_personal_sources
            for task in tasks
        )
        if self._uses_demo_fixture and user.id != "demo-user":
            # The bundled demo rows are templates for each mock crawl owner.
            self._crawled_tasks[user.id] = [
                {**task, "user_id": user.id}
                for task in tasks if task.get("user_id") == "demo-user"
            ]
        self._awaiting_personal_crawl.discard(user.id)
        if "Portal" in enabled_personal_sources:
            self._portal_connected.add(user.id)
        self._last_sync = datetime.now().astimezone()
        return SyncResult(
            ok=True,
            message=(
                f"Mock personal crawl complete: {personal_count} "
                "personal items available"
            ),
        )

    async def load_tasks(self, user):
        raw_tasks = await self.get_tasks(user)
        groups = {"public": [], "personal": []}
        calendar = {"public": [], "personal": []}
        for raw in raw_tasks:
            scope = "personal" if raw.get("user_id") else "public"
            payload = dict(raw)
            try:
                UUID(payload["id"])
            except ValueError:
                payload["id"] = str(uuid5(NAMESPACE_URL, "smart-calendar-mock/" + payload["id"]))
            for field in ("start_time", "end_time"):
                value = payload.get(field)
                if isinstance(value, str):
                    instant = ExtractedTask._to_vn_time(value)
                    payload[field] = {"date": instant.date(), "time": instant.time()}
                elif isinstance(value, dict):
                    payload[field] = {**value, "time": value.get("time", value.get("time_"))}
            payload.setdefault("updated_at", datetime.now().astimezone())
            groups[scope].append(ExtractedTask.model_validate(payload))
            calendar[scope].append(payload)
        scopes = ("public", "personal") if user.id not in self._awaiting_personal_crawl or groups["personal"] else ("public",)
        return bridge_task_load(tuple((scope, groups[scope]) for scope in scopes),
                                [task for scope in scopes for task in calendar[scope]], set())
