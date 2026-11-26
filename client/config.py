from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Runtime settings for the independently deployed web client."""

    mode: str = "mock"
    host: str = "127.0.0.1"
    port: int = 8080
    storage_secret: str = "local-development-secret"
    reload: bool = False

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()
        mode = os.getenv("CLIENT_MODE", "mock").strip().lower()
        if mode not in {"mock", "live"}:
            raise ValueError("CLIENT_MODE must be either 'mock' or 'live'")
        return cls(
            mode=mode,
            host=os.getenv("CLIENT_HOST", "127.0.0.1"),
            port=int(os.getenv("CLIENT_PORT", "8080")),
            storage_secret=os.getenv(
                "CLIENT_STORAGE_SECRET", "local-development-secret"
            ),
            reload=os.getenv("CLIENT_RELOAD", "0") == "1",
        )
