from nicegui import ui


def apply_theme() -> None:
    """Apply Quasar colors inside the active page context."""
    ui.colors(
        primary="#67588f",
        secondary="#547665",
        accent="#b78339",
        positive="#347a62",
        negative="#a34343",
    )

