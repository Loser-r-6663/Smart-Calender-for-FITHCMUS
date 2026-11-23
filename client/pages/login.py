from __future__ import annotations

from dataclasses import asdict

from nicegui import app, ui

from client.components.auth_intro import render_auth_intro
from client.config import AppConfig
from client.core.backend import AuthenticationError, ClientBackend
from client.core.controller import ClientController
from client.theme import apply_theme


def register_login_page(backend: ClientBackend, config: AppConfig) -> None:
    @ui.page("/")
    @ui.page("/login")
    async def login_page() -> None:
        apply_theme()
        if app.storage.user.get("user"):
            ui.navigate.to("/calendar")
            return

        ui.page_title("Sign in · Smart Calendar")
        with ui.element("main").classes("login-page"):
            render_auth_intro()

            with ui.element("section").classes("login-form-wrap"):
                with ui.card().classes("login-card"):
                    ui.label("Welcome back").classes("form-title")
                    ui.label("Sign in to open your calendar.").classes("form-subtitle")
                    account_label = "Email" if config.mode == "live" else "Username"
                    username = ui.input(account_label).props(
                        "outlined autocomplete=username"
                    ).classes("w-full")
                    password = ui.input("Password", password=True).props(
                        "outlined password-toggle"
                    ).classes("w-full")
                    message = ui.label().classes("login-error")
                    message.visible = False

                    controller = ClientController(backend)

                    async def submit() -> None:
                        message.visible = False
                        if not username.value or not password.value:
                            message.text = f"Enter your {account_label.lower()} and password."
                            message.visible = True
                            return
                        login_button.props(add="loading disable")
                        try:
                            user = await controller.login(username.value, password.value)
                            app.storage.user["user"] = asdict(user)
                            ui.navigate.to("/calendar")
                        except AuthenticationError as exc:
                            message.text = str(exc)
                            message.visible = True
                        except Exception:
                            message.text = "The calendar service is unavailable. Try again shortly."
                            message.visible = True
                        finally:
                            login_button.props(remove="loading disable")

                    login_button = ui.button("Sign in", on_click=submit).props(
                        "unelevated no-caps"
                    ).classes("login-button w-full")
                    password.on("keydown.enter", submit)

                    with ui.row().classes("auth-switch items-center justify-center w-full"):
                        ui.label("New here?")
                        ui.link("Create account", "/signup").classes("auth-switch-link")

                    if config.mode == "mock":
                        with ui.element("div").classes("demo-note"):
                            ui.label("Demo account").classes("demo-title")
                            ui.label("student / demo").classes("demo-credentials")
