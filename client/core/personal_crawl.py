from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any


logger = logging.getLogger(__name__)


class PersonalCrawlError(RuntimeError):
    """A crawl failure with a credential-free, user-facing explanation."""


@dataclass(frozen=True)
class PersonalCrawlResult:
    new_count: int
    total_count: int
    failed_sources: tuple[str, ...] = ()

    def __iter__(self):
        yield self.new_count
        yield self.total_count


def log_crawl_failure(source: str, stage: str, error: Exception) -> None:
    # Exception messages and tracebacks can include private browser or task data.
    logger.error("Personal crawl source=%s stage=%s error=%s",
                 source, stage, type(error).__name__)


def run_personal_crawl(
    backend_user: Any,
    access_token: str,
    enabled_sources: set[str],
) -> PersonalCrawlResult:
    """Run Portal/Moodle for one user and persist only that user's tasks.

    This client-owned orchestration supplies the signed-in user's repository and
    access token, keeping personal rows separate from the public task table.
    """
    from DataProcessor.TaskCreator import TaskCreator
    from DataProcessor.Validator import Validator
    from Database.Repository.user_repository import UserRepository
    from Database.Repository.user_task_repository import UserTaskRepository

    if not backend_user.id or not access_token:
        raise PersonalCrawlError("Sign in again before running a personal crawl")

    repository = UserTaskRepository(
        access_token=access_token,
        user_id=str(backend_user.id),
    )
    validator = Validator()
    creator = TaskCreator(backend_user)
    crawlers = creator.crawlers(backend_user)
    extracted_tasks = []
    succeeded_sources: list[str] = []
    failed_sources: list[str] = []

    for platform, crawler in crawlers.items():
        if platform not in enabled_sources:
            continue
        if platform == "Portal" and not (
            backend_user.portal_username
            and backend_user.portal_password
        ):
            backend_user.portal_status = False
            failed_sources.append(platform)
            logger.warning("Personal crawl source=Portal stage=readiness error=MissingCredentials")
            continue
        if platform == "Moodle" and not backend_user.moodle_session:
            backend_user.moodle_status = False
            failed_sources.append(platform)
            logger.warning("Personal crawl source=Moodle stage=readiness error=MissingSession")
            continue

        stage = "fetch"
        try:
            fetched = crawler.fetch_data()
            setattr(backend_user, f"{platform.lower()}_status", True)
            state = getattr(crawler, "state", None)
            if state:
                setattr(backend_user, f"{platform.lower()}_session", json.dumps(state))
            stage = "parse"
            raw_tasks = [
                task.update(platform=platform, updated_at=datetime.now())
                for task in fetched
            ]
            extracted_tasks.extend(creator.parse_tasks(raw_tasks))
        except Exception as error:
            if stage == "fetch":
                setattr(backend_user, f"{platform.lower()}_status", False)
            failed_sources.append(platform)
            log_crawl_failure(platform, stage, error)
            continue

        succeeded_sources.append(platform)

    stage = "save connection status"
    try:
        if not succeeded_sources:
            UserRepository(access_token=access_token).update_user(backend_user)
            raise PersonalCrawlError(
                "Personal crawl failed for all enabled sources. "
                "Reconnect Portal/Moodle in Settings, then retry; check terminal diagnostics."
            )

        stage = "read stored tasks"
        retained_tasks = repository.get_tasks(limit=1000)
        stage = "deduplicate"
        combined_tasks = validator.deduplicate_task(extracted_tasks, retained_tasks)

        new_tasks = [task for task in combined_tasks if task not in retained_tasks]
        stage = "save tasks"
        if new_tasks:
            repository.save_tasks(new_tasks)

        stage = "save connection status"
        UserRepository(access_token=access_token).update_user(backend_user)
    except PersonalCrawlError:
        raise
    except Exception as error:
        log_crawl_failure("personal", stage, error)
        raise PersonalCrawlError(
            f"Personal crawl could not {stage}. Check the service and sign-in, then retry."
        ) from None
    return PersonalCrawlResult(len(new_tasks), len(combined_tasks), tuple(failed_sources))


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
