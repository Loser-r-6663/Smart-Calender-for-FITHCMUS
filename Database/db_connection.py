import os
from contextlib import contextmanager
from typing import Iterator

import psycopg2
from dotenv import load_dotenv
from psycopg2.extensions import connection


class DatabaseConnection:
    def __init__(self) -> None:
        load_dotenv()

    def connect(self) -> connection:
        required_settings = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
        settings = {name: os.getenv(name) for name in required_settings}
        missing_settings = [name for name, value in settings.items() if not value]
        if missing_settings:
            raise ValueError(
                "Missing database configuration: " + ", ".join(missing_settings)
            )

        try:
            port = int(os.getenv("DB_PORT", "5432"))
        except ValueError as error:
            raise ValueError("DB_PORT must be an integer") from error

        return psycopg2.connect(
            host=settings["DB_HOST"],
            dbname=settings["DB_NAME"],
            user=settings["DB_USER"],
            password=settings["DB_PASSWORD"],
            port=port,
        )

    @contextmanager
    def transaction(self) -> Iterator[connection]:
        db_connection = self.connect()
        try:
            yield db_connection
            db_connection.commit()
        except Exception:
            db_connection.rollback()
            raise
        finally:
            db_connection.close()
