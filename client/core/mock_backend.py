from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from DataProcessor.Standardization.ExtractedTask import ExtractedTask

from client.core.backend import AuthenticationError, ClientBackend, RegistrationError, task_load
from client.core.models import ClientUser, ConnectionStatus, SyncResult
from client.core.source_preferences import ALL_SOURCE_NAMES


class MockBackend(ClientBackend):
    """Offline backend used for UI development and browser tests."""

    def __init__(self, fixture_path: Path | None = None) -> None:
        self.fixture_path = fixture_path or (
            Path(__file__).resolve().parents[1] / "fixtures" / "tasks.json"
        )
        self._last_sync: datetime | None = None
        self._disabled_sources: dict[str, set[str]] = {}
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
        self._personal_crawled: set[str] = {demo_user.id}

    async def login(self, username: str, password: str) -> ClientUser:
        await asyncio.sleep(0.2)
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

    async def get_tasks(self, user: ClientUser) -> list[Any]:
        await asyncio.sleep(0.15)
        tasks = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        if user.id not in self._personal_crawled:
            tasks = [
                task
                for task in tasks
                if task.get("source_platform") not in {"Portal", "Moodle"}
            ]
        disabled = await self.get_disabled_sources(user)
        return [task for task in tasks if task.get("source_platform") not in disabled]

    async def load_tasks(self, user: ClientUser):
        tasks = await self.get_tasks(user)
        groups = {"public": [], "personal": []}
        for raw in tasks:
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
            groups[scope].append(ExtractedTask.model_validate(payload))
        scopes = ("public", "personal") if user.id in self._personal_crawled else ("public",)
        return task_load(tuple((scope, groups[scope]) for scope in scopes), set())

    async def get_connection_status(self, user: ClientUser) -> ConnectionStatus:
        return ConnectionStatus(
            portal=user.portal_status or user.id in self._portal_connected,
            moodle=user.moodle_status,
            portal_configured=(
                user.portal_status or user.id in self._portal_configured
            ),
            moodle_configured=user.moodle_status,
            last_sync=self._last_sync,
        )

    async def save_portal_credentials(
        self, user: ClientUser, portal_username: str, portal_password: str
    ) -> SyncResult:
        if not portal_username.strip() or not portal_password:
            return SyncResult(ok=False, message="Enter your Portal ID and password")
        self._portal_configured.add(user.id)
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
        await asyncio.sleep(0.7)
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
        self._personal_crawled.add(user.id)
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
