import asyncio
from datetime import date

from client.core.controller import ClientController
from client.core.mock_backend import MockBackend


def test_mock_controller_loads_and_filters_tasks() -> None:
    async def scenario() -> None:
        controller = ClientController(MockBackend())
        user = await controller.login("student", "demo")
        controller.state.selected_date = date(2026, 11, 23)
        await controller.load_month(date(2026, 11, 1))

        assert user.username == "student"
        assert controller.state.error is None
        assert controller.items_for_date(date(2026, 11, 23))

        controller.set_filter("event")
        assert all(item.kind == "event" for item in controller.filtered_items)

    asyncio.run(scenario())


def test_training_points_respect_month_and_source_preferences() -> None:
    async def scenario() -> None:
        backend = MockBackend()
        controller = ClientController(backend)
        controller.state.user = await controller.login("student", "demo")
        await controller.load_month(date(2026, 11, 1))

        assert controller.training_points_this_month == 13
        assert controller.training_points_overall == 13

        await backend.set_source_enabled(
            controller.state.user, "Phòng Công tác sinh viên", False
        )
        await controller.load_month(date(2026, 11, 1))
        assert controller.training_points_this_month == 8
        assert controller.training_points_overall == 8

        controller.set_filter("class")
        assert controller.training_points_this_month == 8

    asyncio.run(scenario())

