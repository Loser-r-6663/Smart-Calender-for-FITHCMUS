"""Run the live crawler-to-parser pipeline."""

import logging
import sys
from pathlib import Path

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


def main() -> int:
    _configure_logging()
    try:
        load_dotenv(ROOT / ".env")
        _ensure_crawler_runtime_directories()
        LOGGER.info("pipeline=start")

        parser = ParserManager.from_env()
        creator = TaskCreator()
        crawler_results = creator.crawl_raw_task()
        source_counts = {
            source: len(records) for source, records in crawler_results.items()
        }
        LOGGER.info(
            "crawler=complete total=%d sources=%s",
            sum(source_counts.values()),
            source_counts,
        )

        batch = parser.process_crawler_results(crawler_results)
        LOGGER.info(
            "batch processed=%d skipped=%d failed=%d persisted=%d status=%s",
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
        return 0 if batch.failed == 0 and getattr(batch.status, "value", batch.status) != "failed" else 1
    except Exception as exc:
        LOGGER.error("pipeline failed: %s: %s", type(exc).__name__, _safe_message(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
