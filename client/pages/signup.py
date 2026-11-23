from __future__ import annotations

from dataclasses import asdict

from nicegui import app, ui

from client.components.auth_intro import render_auth_intro
from client.config import AppConfig
from client.core.backend import ClientBackend, RegistrationError
from client.core.models import ClientUser
from client.theme import apply_theme


def register_signup_page(backend: ClientBackend, config: AppConfig) -> None:
    @ui.page("/signup")
    async def signup_page() -> None:
        apply_theme()
        if app.storage.user.get("user"):
            ui.navigate.to("/calendar")
            return

        ui.page_title("Create account · Smart Calendar")
        with ui.element("main").classes("login-page"):
            render_auth_intro()

            with ui.element("section").classes("login-form-wrap"):
                with ui.card().classes("login-card"):
                    ui.label("Create account").classes("form-title")
                    ui.label("Set up your Smart Calendar login.").classes(
                        "form-subtitle"
                    )
                    account_label = "Email" if config.mode == "live" else "Username"
                    username = ui.input(account_label).props(
                        "outlined autocomplete=username"
                    ).classes("w-full")
                    password = ui.input("Password", password=True).props(
                        "outlined password-toggle autocomplete=new-password"
                    ).classes("w-full")
                    confirmation = ui.input("Confirm password", password=True).props(
                        "outlined password-toggle autocomplete=new-password"
                    ).classes("w-full")
                    message = ui.label().classes("login-error")
                    message.visible = False

                    async def submit() -> None:
                        message.visible = False
                        clean_username = (username.value or "").strip()
                        if config.mode == "live" and "@" not in clean_username:
                            message.text = "Enter a valid email address."
                            message.visible = True
                            return
                        if len(clean_username) < 3:
                            message.text = f"{account_label} must contain at least 3 characters."
                            message.visible = True
                            return
                        if len(password.value or "") < 8:
                            message.text = "Password must contain at least 8 characters."
                            message.visible = True
                            return
                        if password.value != confirmation.value:
                            message.text = "Passwords do not match."
                            message.visible = True
                            return

                        signup_button.props(add="loading disable")
                        try:
                            previous = app.storage.user.pop("user", None)
                            if previous:
                                backend.logout(ClientUser(**previous))
                            user = await backend.register(clean_username, password.value)
                            app.storage.user["user"] = asdict(user)
                            password.value = ""
                            confirmation.value = ""
                            ui.navigate.to("/settings")
                        except RegistrationError as exc:
                            message.text = str(exc)
                            message.visible = True
                        except Exception:
                            message.text = (
                                "The account service is unavailable. Try again shortly."
                            )
                            message.visible = True
                        finally:
                            signup_button.props(remove="loading disable")

                    signup_button = ui.button(
                        "Create account", on_click=submit
                    ).props("unelevated no-caps").classes("login-button w-full")
                    confirmation.on("keydown.enter", submit)

                    with ui.row().classes(
                        "auth-switch items-center justify-center w-full"
                    ):
                        ui.label("Already registered?")
                        ui.link("Sign in", "/login").classes("auth-switch-link")
