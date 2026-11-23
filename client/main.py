from __future__ import annotations

from pathlib import Path

from nicegui import ui

from client.config import AppConfig
from client.core.live_backend import LiveBackend
from client.core.mock_backend import MockBackend
from client.pages.calendar import register_calendar_page
from client.pages.login import register_login_page
from client.pages.settings import register_settings_page
from client.pages.signup import register_signup_page


def create_app() -> AppConfig:
    config = AppConfig.from_env()
    backend = MockBackend() if config.mode == "mock" else LiveBackend()

    css_path = Path(__file__).parent / "static" / "styles.css"
    ui.add_css(css_path, shared=True)

    register_login_page(backend, config)
    register_signup_page(backend, config)
    register_calendar_page(backend, config)
    register_settings_page(backend, config)
    return config


def main() -> None:
    config = create_app()
    ui.run(
        host=config.host,
        port=config.port,
        title="Smart Calendar",
        favicon="📅",
        storage_secret=config.storage_secret,
        reload=config.reload,
        show=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
