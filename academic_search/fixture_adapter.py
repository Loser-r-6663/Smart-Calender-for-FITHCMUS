"""Isolated in-memory read projection for tests/demo, not a production migration."""
import json
import sqlite3

from .service import (SOURCES, STATUSES, TIME_FIELDS, TYPES,
                      check, instant, validate_task_id)

PROJECTION_FIELDS = ("id", "type", "course_code", "source_platform", "status", "training_points",
                     "target_audience", "location", *TIME_FIELDS)


def create_demo_database(tasks):
    """Create a fresh :memory: database. Never opens a filesystem/user database."""
    connection = sqlite3.connect(":memory:")
    connection.execute("""CREATE TABLE search_tasks (
        id TEXT PRIMARY KEY, payload TEXT NOT NULL,
        type TEXT NOT NULL, course_code TEXT, source_platform TEXT NOT NULL,
        status TEXT NOT NULL, training_points INTEGER, target_audience TEXT, location TEXT,
        deadline INTEGER, registration_start INTEGER, registration_end INTEGER,
        start_time INTEGER, end_time INTEGER, updated_at INTEGER NOT NULL
    )""")
    try:
        with connection:
            for task in tasks:
                store_task(connection, task)
    except Exception:
        connection.close()
        raise
    return connection


def store_task(connection, task):
    """Insert/replace a fixture projection; caller owns the transaction.

    Preserve the original task document and null points; normalize only the SQL
    comparison columns. This is an adapter, not another production Task model.
    """
    check(isinstance(task, dict) and set(PROJECTION_FIELDS) <= task.keys(), "task missing projection fields")
    validate_task_id(task["id"])
    check(task["type"] in TYPES and task["status"] in STATUSES and task["source_platform"] in SOURCES, "invalid task enum")
    points = task["training_points"]
    check(points is None or (type(points) is int and 0 <= points <= 100), "invalid task points")
    values = {key: task[key] for key in PROJECTION_FIELDS}
    for key in TIME_FIELDS:
        values[key] = None if task[key] is None else instant(task[key])
    check(values["updated_at"] is not None, "updated_at is required")
    for start, end in (("start_time", "end_time"), ("registration_start", "registration_end")):
        if values[start] is not None and values[end] is not None:
            check(values[start] < values[end], f"{start} must precede {end}")
    if task["type"] in {"assignment", "tuition"}:
        check(values["deadline"] is not None, "assignment/tuition requires deadline")
    columns = ("payload", *PROJECTION_FIELDS)
    assignments = ", ".join(f"{column}=excluded.{column}" for column in columns if column != "id")
    connection.execute(
        f"INSERT INTO search_tasks ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)}) "
        f"ON CONFLICT(id) DO UPDATE SET {assignments}",
        [json.dumps(task, ensure_ascii=False), *(values[key] for key in PROJECTION_FIELDS)],
    )
