import json
import logging
import os
import sys
from pathlib import Path

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


def delete_record(
    client: TestClient,
    state: dict[str, str | int | None],
    record_type: str,
    record_id: str | int,
) -> None:
    response = client.delete(f"/{record_type}/{record_id}")
    logger.info(
        "DELETE /%s/%s -> %s: %s",
        record_type,
        record_id,
        response.status_code,
        response.text or "(empty response)",
    )
    if response.status_code != 204:
        raise RuntimeError(
            f"Could not delete test {record_type[:-1]} {record_id}: "
            f"HTTP {response.status_code} {response.text}"
        )

    state[f"{record_type[:-1]}_id"] = None
    save_state(state)
    print(f"Deleted {record_type[:-1]}: {record_id}")


def main() -> None:
    if os.getenv("RUN_API_CRUD_TESTS") != "1":
        raise SystemExit(
            "Not running: set RUN_API_CRUD_TESTS=1 to enable API deletes."
        )
    admin_key = os.getenv("ADMIN_API_KEY")
    if not admin_key:
        raise SystemExit("Set ADMIN_API_KEY in .env to run this admin-only script.")
    if not STATE_FILE.exists():
        raise FileNotFoundError(
            f"{STATE_FILE.name} was not found. Run test_api_create_records.py first."
        )

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    task_id = state.get("task_id")
    user_id = state.get("user_id")
    if task_id is None and user_id is None:
        raise ValueError(f"{STATE_FILE.name} contains no records to delete.")

    with TestClient(
        app,
        headers={"Authorization": f"Bearer {admin_key}"},
    ) as client:
        if task_id is not None:
            delete_record(client, state, "tasks", task_id)
        if user_id is not None:
            delete_record(client, state, "users", user_id)

    STATE_FILE.unlink()
    print("All created test records were deleted; saved IDs file removed.")


if __name__ == "__main__":
    main()
