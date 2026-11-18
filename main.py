"""Run the live crawler-to-parser-to-scheduler pipeline."""

import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from Backend.Parser import ParserManager
from Backend.TaskCreator import TaskCreator


ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("live_pipeline")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stdout,
    )


def _safe_message(value: object) -> str:
    return " ".join(str(value).split())[:500]


def _ensure_crawler_runtime_directories() -> None:
    for directory in (
        ROOT / "Backend" / "Crawler" / "State",
        ROOT / "Backend" / "Crawler" / "History",
    ):
        directory.mkdir(parents=True, exist_ok=True)


def _ensure_target_user(client: Any, user_id: int) -> int:
    """Ensure target user exists in database; if not, find existing or create default user."""
    try:
        user = client.get_user(user_id)
        if user and user.get("id"):
            return int(user["id"])
    except Exception:
        pass

    for probe_id in range(1, 21):
        if probe_id == user_id:
            continue
        try:
            user = client.get_user(probe_id)
            if user and user.get("id"):
                LOGGER.info("using existing database user id=%d", probe_id)
                return int(user["id"])
        except Exception:
            continue

    try:
        import time
        unique_suffix = f"{user_id}_{int(time.time())}"
        created = client.create_user({
            "username": f"student_{unique_suffix}",
            "email": f"student_{unique_suffix}@fit.hcmus.edu.vn",
            "full_name": f"FIT Student {user_id}",
        })
        new_id = int(created.get("id", user_id))
        LOGGER.info("user created id=%d username=%s", new_id, created.get("username"))
        return new_id
    except Exception as exc:
        LOGGER.warning("could not ensure user %d: %s", user_id, _safe_message(exc))
        return user_id


def main() -> int:
    _configure_logging()
    try:
        load_dotenv(ROOT / ".env")
        _ensure_crawler_runtime_directories()
        LOGGER.info("pipeline=start")

        # 1. Initialize Parser & Database Client
        parser = ParserManager.from_env()

        # 2. Crawler Stage
        LOGGER.info("stage=crawler start")
        creator = TaskCreator(include_all_fb_pages=True)
        crawler_results = creator.crawl_raw_task()
        source_counts = {
            source: len(records) for source, records in crawler_results.items()
        }
        LOGGER.info(
            "stage=crawler complete total=%d sources=%s",
            sum(source_counts.values()),
            source_counts,
        )

        # 3. Parser & Database Persistence Stage
        LOGGER.info("stage=parser_and_database start")
        batch = parser.process_crawler_results(crawler_results)
        LOGGER.info(
            "stage=parser_and_database complete processed=%d skipped=%d failed=%d persisted=%d status=%s",
            batch.processed,
            batch.skipped,
            batch.failed,
            batch.persisted,
            getattr(batch.status, "value", batch.status),
        )
        for index, item in enumerate(batch.items, 1):
            if item.error is not None:
                raw = getattr(item, "raw", None)
                source = getattr(raw, "source_alias", None) or "unknown"
                LOGGER.error(
                    "item=%d source=%s error=%s: %s",
                    index,
                    source,
                    _safe_message(item.error.type),
                    _safe_message(item.error.message),
                )

        if batch.failed > 0 or getattr(batch.status, "value", batch.status) == "failed":
            LOGGER.warning("crawler/parser encountered errors, continuing to scheduler...")

        # 4. Scheduling Stage (Branch and Bound DRL Optimization)
        target_user_id = int(os.getenv("SCHEDULE_USER_ID", "1"))
        LOGGER.info("stage=scheduler start user_id=%d", target_user_id)
        if parser.database_api is not None:
            resolved_user_id = _ensure_target_user(parser.database_api, target_user_id)
            try:
                schedule = parser.database_api.schedule_user(
                    resolved_user_id, {"persist": True}
                )
                LOGGER.info(
                    "stage=scheduler complete status=%s week=%s..%s tasks_loaded=%d prepared=%d drl_gained=+%d total_drl=%d",
                    schedule.get("status"),
                    schedule.get("week_start"),
                    schedule.get("week_end"),
                    schedule.get("total_tasks_loaded", 0),
                    schedule.get("prepared_tasks_count", 0),
                    schedule.get("total_drl_gained", 0),
                    schedule.get("final_total_drl", 0),
                )
                events = schedule.get("selected_events", [])
                if events:
                    print("\n" + "=" * 75)
                    print(f" OPTIMAL SCHEDULE (User {resolved_user_id}) - Week {schedule.get('week_start')} -> {schedule.get('week_end')}")
                    print(f" Total DRL Gained: +{schedule.get('total_drl_gained')} | Final DRL: {schedule.get('final_total_drl')} pts")
                    print(f" Breakdown: {schedule.get('final_drl')}")
                    print("-" * 75)
                    for ev in events:
                        start_str = ev.get("start_time", "")[:16].replace("T", " ")
                        end_str = ev.get("end_time", "")[11:16]
                        print(f"  * [{start_str} - {end_str}] {ev.get('title')}")
                        print(f"    Location: {ev.get('location')} | DRL: +{ev.get('points_gained')} ({ev.get('drl_category')})")
                    print("=" * 75 + "\n")
                else:
                    LOGGER.info("No DRL events selected or no events within the current week window.")
            except Exception as sched_err:
                LOGGER.error("stage=scheduler failed: %s: %s", type(sched_err).__name__, _safe_message(sched_err))
                return 1

        LOGGER.info("pipeline=complete")
        return 0
    except Exception as exc:
        LOGGER.error("pipeline failed: %s: %s", type(exc).__name__, _safe_message(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
