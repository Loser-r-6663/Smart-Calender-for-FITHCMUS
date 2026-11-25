from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any

from client.core.models import (
    ClientUser,
    ConnectionStatus,
    ScheduleViewData,
    SyncResult,
    TaskDraft,
)


class AuthenticationError(ValueError):
    pass


class RegistrationError(ValueError):
    pass


class ClientBackend(ABC):
    """The only backend contract visible to the web client."""

    @abstractmethod
    async def login(self, username: str, password: str) -> ClientUser:
        raise NotImplementedError

    @abstractmethod
    async def register(self, username: str, password: str) -> ClientUser:
        """Create a user in the backend's custom users table."""
        raise NotImplementedError

    @abstractmethod
    async def change_password(
        self, user: ClientUser, current_password: str, new_password: str
    ) -> SyncResult:
        """Verify the current password and replace the calendar password."""
        raise NotImplementedError

    @abstractmethod
    async def get_tasks(self, user: ClientUser) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    async def create_task(self, user: ClientUser, task: TaskDraft) -> SyncResult:
        raise NotImplementedError

    @abstractmethod
    async def update_task(
        self, user: ClientUser, task_id: str, task: TaskDraft
    ) -> SyncResult:
        raise NotImplementedError

    @abstractmethod
    async def delete_task(self, user: ClientUser, task_id: str) -> SyncResult:
        raise NotImplementedError

    @abstractmethod
    async def run_schedule(
        self, user: ClientUser, week_anchor: date | None = None
    ) -> ScheduleViewData:
        """Run BranchAndBoundScheduler for the requested week and return view data."""
        raise NotImplementedError

    @abstractmethod
    async def set_task_schedule_state(
        self,
        user: ClientUser,
        task_id: str,
        *,
        status: str | None = None,
        compulsory: bool | None = None,
    ) -> SyncResult:
        """Remove/restore a task from scheduling or toggle compulsory pinning."""
        raise NotImplementedError

    @abstractmethod
    async def get_initial_drl(self, user: ClientUser) -> dict[str, int]:
        """Return the user's baseline training points per Article."""
        raise NotImplementedError

    @abstractmethod
    async def save_initial_drl(
        self, user: ClientUser, points: dict[str, int]
    ) -> SyncResult:
        """Persist the user's baseline training points per Article."""
        raise NotImplementedError

    @abstractmethod
    async def get_connection_status(self, user: ClientUser) -> ConnectionStatus:
        raise NotImplementedError

    @abstractmethod
    async def save_portal_credentials(
        self, user: ClientUser, portal_username: str, portal_password: str
    ) -> SyncResult:
        """Store encrypted Portal credentials for later crawler verification."""
        raise NotImplementedError

    @abstractmethod
    async def connect_moodle(self, user: ClientUser) -> SyncResult:
        """Open a local browser for Moodle's Google sign-in and save its session."""
        raise NotImplementedError

    @abstractmethod
    async def get_disabled_sources(self, user: ClientUser) -> set[str]:
        """Return source subscriptions disabled for this user."""
        raise NotImplementedError

    @abstractmethod
    async def set_source_enabled(
        self, user: ClientUser, source_name: str, enabled: bool
    ) -> None:
        """Persist one per-user source subscription preference."""
        raise NotImplementedError

    @abstractmethod
    async def set_all_sources_enabled(
        self, user: ClientUser, enabled: bool
    ) -> None:
        """Persist all per-user source subscription preferences."""
        raise NotImplementedError

    @abstractmethod
    async def sync(self, user: ClientUser, scope: str = "all") -> SyncResult:
        raise NotImplementedError
