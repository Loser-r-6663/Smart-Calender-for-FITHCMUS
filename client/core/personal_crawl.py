from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def run_personal_crawl(
    backend_user: Any,
    access_token: str,
    enabled_sources: set[str],
) -> tuple[int, int]:
    """Run Portal/Moodle for one user and persist only that user's tasks.

    The crawler implementation remains imported unchanged from crawler-branch.
    This client-owned orchestration supplies the signed-in user's repository and
    access token, keeping personal rows separate from the public task table.
    """
    from Backend.TaskCreator import TaskCreator
    from Backend.Validator import Validator
    from Database.Repository.user_repository import UserRepository
    from Database.Repository.user_task_repository import UserTaskRepository

    if not backend_user.id:
        raise ValueError("A backend user ID is required for personal crawling")

    repository = UserTaskRepository(
        access_token=access_token,
        user_id=str(backend_user.id),
    )
    validator = Validator()
    creator = TaskCreator(backend_user)
    crawlers = creator.crawlers(backend_user)
    raw_tasks = []
    succeeded_sources: list[str] = []

    for platform, crawler in crawlers.items():
        if platform not in enabled_sources:
            continue
        if platform == "Portal" and not (
            backend_user.portal_username
            and backend_user.portal_password
            and backend_user.portal_session
        ):
            backend_user.portal_status = False
            continue
        if platform == "Moodle" and not backend_user.moodle_session:
            backend_user.moodle_status = False
            continue

        # The imported crawler uses an actor-wide state key in server mode.
        # Override only this instance's state loader so each signed-in user
        # crawls with the session stored on their own user record.
        crawler.get_state = lambda current=crawler: current.state
        try:
            fetched = crawler.fetch_data()
        except Exception:
            setattr(backend_user, f"{platform.lower()}_status", False)
            continue

        setattr(backend_user, f"{platform.lower()}_status", True)
        state = getattr(crawler, "state", None)
        if state:
            setattr(backend_user, f"{platform.lower()}_session", json.dumps(state))
        raw_tasks.extend(
            task.update(platform=platform, updated_at=datetime.now())
            for task in fetched
        )
        succeeded_sources.append(platform)

    if not succeeded_sources:
        UserRepository(access_token=access_token).update_user(backend_user)
        raise RuntimeError("No configured personal crawler has a valid session")

    extracted_tasks = creator.parse_tasks(raw_tasks)
    retained_tasks = repository.get_tasks(limit=1000)
    combined_tasks = validator.deduplicate_task(extracted_tasks, retained_tasks)

    expired_tasks = validator.filter_expired_tasks(combined_tasks)
    if expired_tasks:
        repository.delete_tasks(expired_tasks)

    new_tasks = [
        task
        for task in combined_tasks
        if task not in retained_tasks and task not in expired_tasks
    ]
    if new_tasks:
        repository.save_tasks(new_tasks)

    # Persist refreshed sessions and connection status on the same user row.
    UserRepository(access_token=access_token).update_user(backend_user)
    return len(new_tasks), len(combined_tasks) - len(expired_tasks)
