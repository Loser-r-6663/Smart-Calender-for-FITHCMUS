import asyncio

from client.core.mock_backend import MockBackend
from client.core.models import ClientUser
from client.core.source_preferences import ALL_SOURCE_NAMES


def test_registry_contains_every_crawler_source() -> None:
    assert len(ALL_SOURCE_NAMES) == 13
    assert "Portal" in ALL_SOURCE_NAMES
    assert "Moodle" in ALL_SOURCE_NAMES
    assert "Facebook Khoa Công nghệ thông tin" in ALL_SOURCE_NAMES


def test_every_crawler_source_has_an_external_url() -> None:
    from client.core.source_preferences import SOURCE_GROUPS

    sources = [source for _, group in SOURCE_GROUPS for source in group]
    assert all(source.url.startswith("https://") for source in sources)


def test_source_preferences_are_per_user_and_filter_backend_results() -> None:
    async def scenario() -> None:
        backend = MockBackend()
        first = ClientUser(id="first", username="first")
        second = ClientUser(id="second", username="second")
        for user in (first, second):
            await backend.save_portal_credentials(user, "fictional-student", "fictional-password")
            assert (await backend.sync(user)).ok

        await backend.set_source_enabled(first, "Moodle", False)
        assert await backend.get_disabled_sources(first) == {"Moodle"}
        assert await backend.get_disabled_sources(second) == set()
        assert all(
            task.get("source_platform") != "Moodle"
            for task in await backend.get_tasks(first)
        )
        assert any(
            task.get("source_platform") == "Moodle"
            for task in await backend.get_tasks(second)
        )

        await backend.set_all_sources_enabled(first, False)
        assert await backend.get_disabled_sources(first) == set(ALL_SOURCE_NAMES)
        assert await backend.get_tasks(first) == []

        await backend.set_all_sources_enabled(first, True)
        assert await backend.get_disabled_sources(first) == set()

    asyncio.run(scenario())
