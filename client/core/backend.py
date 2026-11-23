from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from client.core.models import ClientUser, ConnectionStatus, SyncResult


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
    async def get_connection_status(self, user: ClientUser) -> ConnectionStatus:
        raise NotImplementedError

    @abstractmethod
    async def save_portal_credentials(
        self, user: ClientUser, portal_username: str, portal_password: str
    ) -> SyncResult:
        """Store encrypted Portal credentials for later crawler verification."""
        raise NotImplementedError

    # Moodle connection is intentionally unsupported for now. Its crawler
    # requires an interactive Google authorization session that cannot be
    # completed through the current remotely deployed backend.

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
