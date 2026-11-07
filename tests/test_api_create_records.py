import json
import logging
import os
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Database.api import app


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)
STATE_FILE = Path(__file__).with_name(".api_crud_test_state.json")


def save_state(state: dict[str, str | int | None]) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    if os.getenv("RUN_API_CRUD_TESTS") != "1":
        raise SystemExit(
            "Not running: set RUN_API_CRUD_TESTS=1 to enable API writes."
        )
    admin_key = os.getenv("ADMIN_API_KEY")
    if not admin_key:
        raise SystemExit("Set ADMIN_API_KEY in .env to run this admin-only script.")
    if STATE_FILE.exists():
        raise RuntimeError(
            f"{STATE_FILE.name} already exists. Delete those records first "
            "before creating another set."
        )

    state: dict[str, str | int | None] = {"task_id": None, "user_id": None}

    with TestClient(
        app,
        headers={"Authorization": f"Bearer {admin_key}"},
    ) as client:
        task_id = f"api-test-{uuid4().hex}"
        task_response = client.post(
            "/tasks",
            json={
                "id": task_id,
                "title": "API CRUD test task",
                "type": "personal",
            },
        )
        logger.info(
            "POST /tasks -> %s: %s",
            task_response.status_code,
            task_response.text,
        )
        task_response.raise_for_status()
        if task_response.status_code != 201:
            raise RuntimeError(
                f"Unexpected task creation status: {task_response.status_code}"
            )
        state["task_id"] = task_id
        save_state(state)
        print("Created task:")
        print(json.dumps(task_response.json(), ensure_ascii=False, indent=2))

        token = uuid4().hex
        user_response = client.post(
            "/users",
            json={
                "username": f"api_test_{token[:16]}",
                "email": f"api_test_{token}@example.edu",
                "full_name": "API CRUD test user",
            },
        )
        logger.info(
            "POST /users -> %s: %s",
            user_response.status_code,
            user_response.text,
        )
        user_response.raise_for_status()
        if user_response.status_code != 201:
            raise RuntimeError(
                f"Unexpected user creation status: {user_response.status_code}"
            )
        created_user = user_response.json()
        state["user_id"] = created_user["id"]
        save_state(state)
        print("Created user:")
        print(json.dumps(created_user, ensure_ascii=False, indent=2))

    print(f"IDs saved in {STATE_FILE}")


if __name__ == "__main__":
    main()
