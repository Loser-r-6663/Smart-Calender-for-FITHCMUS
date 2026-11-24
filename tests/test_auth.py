from __future__ import annotations

import asyncio

import pytest

from client.core.backend import RegistrationError
from client.core.mock_backend import MockBackend


def test_registered_mock_user_can_sign_in() -> None:
    async def scenario() -> None:
        backend = MockBackend()
        registered = await backend.register("newstudent", "password123")
        signed_in = await backend.login("newstudent", "password123")

        assert signed_in == registered

    asyncio.run(scenario())


def test_mock_registration_rejects_duplicate_username() -> None:
    async def scenario() -> None:
        backend = MockBackend()
        with pytest.raises(RegistrationError, match="already taken"):
            await backend.register("student", "another-password")

    asyncio.run(scenario())


def test_portal_credentials_are_configured_but_not_verified() -> None:
    async def scenario() -> None:
        backend = MockBackend()
        user = await backend.register("newstudent", "password123")

        result = await backend.save_portal_credentials(
            user, "23123456", "portal-secret"
        )
        status = await backend.get_connection_status(user)

        assert result.ok is True
        assert status.portal_configured is True
        assert status.portal is False

    asyncio.run(scenario())


def test_mock_moodle_connection_is_available() -> None:
    async def scenario() -> None:
        backend = MockBackend()
        user = await backend.register("newstudent", "password123")

        result = await backend.connect_moodle(user)
        status = await backend.get_connection_status(user)

        assert result.ok is True
        assert status.moodle_configured is True
        assert status.moodle is True

    asyncio.run(scenario())


def test_mock_password_change_requires_current_password() -> None:
    async def scenario() -> None:
        backend = MockBackend()
        user = await backend.register("newstudent", "password123")

        result = await backend.change_password(user, "wrong-password", "updated123")

        assert result.ok is False
        assert result.message == "Current password is incorrect"

    asyncio.run(scenario())


def test_mock_password_change_replaces_login_password() -> None:
    async def scenario() -> None:
        backend = MockBackend()
        user = await backend.register("newstudent", "password123")

        result = await backend.change_password(user, "password123", "updated123")
        signed_in = await backend.login("newstudent", "updated123")

        assert result.ok is True
        assert signed_in == user

    asyncio.run(scenario())
