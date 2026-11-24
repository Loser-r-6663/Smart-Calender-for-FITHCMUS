from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any


logger = logging.getLogger(__name__)


def run_personal_crawl(
    backend_user: Any,
    access_token: str,
    enabled_sources: set[str],
) -> tuple[int, int]:
    """Run Portal/Moodle for one user and persist only that user's tasks.

    The crawler implementation remains imported unchanged from DataProcessor.
    This client-owned orchestration supplies the signed-in user's repository and
    access token, keeping personal rows separate from the public task table.
    """
    from DataProcessor.TaskCreator import TaskCreator
    from DataProcessor.Validator import Validator
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
        ):
            backend_user.portal_status = False
            continue
        if platform == "Moodle" and not backend_user.moodle_session:
            backend_user.moodle_status = False
            continue

        try:
            fetched = crawler.fetch_data()
        except Exception:
            setattr(backend_user, f"{platform.lower()}_status", False)
            logger.exception("Personal crawler failed for %s", platform)
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
    retained_tasks = repository.get_tasks(limit=None)
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


def capture_moodle_session(backend_user: Any) -> str:
    """Run Moodle's interactive sign-in in a local browser and return its state."""
    from DataProcessor.Crawler.MoodleCrawler import MoodleCrawler

    crawler = MoodleCrawler(backend_user)
    with crawler.load_engine() as playwright:
        crawler.crawler = playwright
        crawler.authenticate()

    if not crawler.state:
        raise RuntimeError("Moodle did not return an authenticated browser session")
    return json.dumps(crawler.state)
