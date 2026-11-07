"""Run the crawler output through the real parser and task API pipeline. Uses the debug output from the Crawler"""

import ast
import logging
from pathlib import Path
import re
import sys
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Parser import ParserManager, PipelineStage, RawCrawlerInput, StageStatus


DEFAULT_INPUT = ROOT / "Backend" / "Crawler" / "RawTasks.txt"
LOGGER = logging.getLogger("pipeline_demo")
_TASK_START = re.compile(r"(?m)^[ \t]*RawTask\(")
_FIELD = re.compile(r"^[ \t]*([A-Za-z_]\w*)[ \t]*:[ \t]*(.*)$")
_STAGE_LABELS = {
    PipelineStage.ADAPT: "crawler adaptation",
    PipelineStage.API_HEALTH: "database API health check",
    PipelineStage.DUPLICATE: "deduplication (canonical URL + SHA-256)",
    PipelineStage.PARSE: "AI extraction + provider schema validation",
    PipelineStage.CANDIDATE_DEDUP: "candidate deduplication",
    PipelineStage.PREPARE: "database payload preparation",
    PipelineStage.SEND: "database validation + persistence",
    PipelineStage.REMEMBER: "fingerprint remembrance",
}


class RawTasksFormatError(ValueError):
    """Raised when the crawler's printed representation is malformed."""


class LoggingParserManager(ParserManager):
    """Add concise live stage logging without changing production orchestration."""

    @staticmethod
    def _stage_context(value: Any) -> str:
        if isinstance(value, RawCrawlerInput):
            source = value.source_alias or "unknown"
            url = f" url={value.source_url}" if value.source_url else ""
            return f" source={source}{url}"
        if isinstance(value, dict) and "candidate" in value:
            candidate = value["candidate"]
            title = getattr(candidate, "title", "unknown")
            index = value.get("candidate_index", "?")
            source = getattr(candidate, "source_platform", "unknown")
            source = getattr(source, "value", source)
            url = getattr(candidate, "source_url", None)
            url_context = f" url={url}" if url else ""
            return f" candidate={index} source={source} title={title!r}{url_context}"
        return ""

    @staticmethod
    def _stage(
        stage: PipelineStage,
        value: Any,
        operation: Any,
    ):
        label = _STAGE_LABELS[stage]
        context = LoggingParserManager._stage_context(value)
        LOGGER.info("stage=%s label=%r%s status=started", stage.value.upper(), label, context)
        result = ParserManager._stage(stage, value, operation)
        if result.status is StageStatus.FAILED:
            error = result.error
            LOGGER.info(
                "stage=%s label=%r%s status=failed elapsed_ms=%.1f error=%s: %s",
                stage.value.upper(),
                label,
                context,
                result.elapsed_ms,
                error.type,
                error.message,
            )
        else:
            completion = ""
            if (
                stage is PipelineStage.CANDIDATE_DEDUP
                and result.status is StageStatus.SUCCESS
            ):
                completion = (
                    f" kept={len(result.output)}"
                    f" removed={len(result.input) - len(result.output)}"
                )
            LOGGER.info(
                "stage=%s label=%r%s status=%s elapsed_ms=%.1f%s",
                stage.value.upper(),
                label,
                context,
                result.status.value,
                result.elapsed_ms,
                completion,
            )
        return result


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _raw_task_end(text: str, opening: int) -> int:
    depth = 1
    quote: str | None = None
    escaped = False
    for index in range(opening + 1, len(text)):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    raise RawTasksFormatError(
        f"unterminated RawTask block near line {_line_number(text, opening)}"
    )


def _task_dict(text: str, start: int, end: int) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    task_start = text.index("RawTask(", start, end)
    body = text[task_start + len("RawTask(") : end]
    body_start_line = _line_number(text, start)
    for offset, line in enumerate(body.splitlines(), body_start_line):
        stripped = line.strip()
        if not stripped or stripped in {",", ")"}:
            continue
        match = _FIELD.match(line)
        if not match:
            raise RawTasksFormatError(
                f"malformed field near line {offset}: {stripped[:120]}"
            )
        name, source = match.groups()
        try:
            fields[name] = ast.literal_eval(source)
        except (SyntaxError, ValueError) as exc:
            raise RawTasksFormatError(
                f"invalid value for {name!r} near line {offset}: {source[:120]}"
            ) from exc
    return fields


def parse_raw_tasks(text: str) -> dict[str, list[dict[str, Any]]]:
    """Convert the crawler's custom repr to validated plain dictionaries."""
    transformed: list[str] = []
    cursor = 0
    for match in _TASK_START.finditer(text):
        transformed.append(text[cursor : match.start()])
        opening = match.end() - 1
        end = _raw_task_end(text, opening)
        transformed.append(repr(_task_dict(text, match.start(), end)))
        cursor = end + 1
    transformed.append(text[cursor:])
    try:
        result = ast.literal_eval("".join(transformed))
    except (SyntaxError, ValueError) as exc:
        line = getattr(exc, "lineno", "unknown")
        raise RawTasksFormatError(
            f"invalid outer mapping near line {line}: {exc}"
        ) from exc
    if not isinstance(result, dict) or any(
        not isinstance(source, str)
        or not isinstance(records, list)
        or any(not isinstance(record, dict) for record in records)
        for source, records in result.items()
    ):
        raise RawTasksFormatError("expected a dict[str, list[dict]]")
    return result


def _log_item(index: int, item: Any) -> None:
    source = item.raw.source_alias or "unknown"
    stages = ", ".join(
        f"{stage.stage.value}:{stage.status.value}/{stage.elapsed_ms:.0f}ms"
        for stage in item.stages
        if stage.stage is not None
    )
    error = f" error={item.error.type}: {item.error.message}" if item.error else ""
    ids = [record.get("id") for record in item.persisted if record.get("id")]
    parsed_count = next(
        (len(stage.output) for stage in item.stages
         if stage.stage is PipelineStage.PARSE and stage.status is StageStatus.SUCCESS),
        len(item.candidates),
    )
    dedup_count = next(
        (len(stage.output) for stage in item.stages
         if stage.stage is PipelineStage.CANDIDATE_DEDUP
         and stage.status is StageStatus.SUCCESS),
        len(item.candidates),
    )
    LOGGER.info(
        "item=%d source=%s status=%s stages=[%s] candidates=%d kept=%d removed=%d persisted=%d ids=%s%s",
        index,
        source,
        item.status.value,
        stages,
        len(item.candidates),
        dedup_count,
        parsed_count - dedup_count,
        len(item.persisted),
        ids,
        error,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stdout,
    )
    arguments = argv if argv is not None else sys.argv[1:]
    input_path = Path(arguments[0]).expanduser() if arguments else DEFAULT_INPUT
    if not input_path.is_absolute():
        input_path = input_path.resolve()
    LOGGER.info("input=%s", input_path)
    load_dotenv(ROOT / ".env")
    results = parse_raw_tasks(input_path.read_text(encoding="utf-8"))
    counts = {key: len(value) for key, value in results.items()}
    LOGGER.info("records=%d sources=%s", sum(counts.values()), counts)
    LOGGER.info("pipeline=start")
    batch = LoggingParserManager.from_env().process_crawler_results(results)
    for index, item in enumerate(batch.items, 1):
        _log_item(index, item)
    LOGGER.info(
        "batch processed=%d skipped=%d failed=%d persisted=%d status=%s",
        batch.processed,
        batch.skipped,
        batch.failed,
        batch.persisted,
        batch.status.value,
    )
    return 0 if batch.failed == 0 and batch.status is not StageStatus.FAILED else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.basicConfig(
            level=logging.ERROR,
            format="%(levelname)s %(message)s",
            stream=sys.stdout,
        )
        LOGGER.error("pipeline failed: %s: %s", type(exc).__name__, " ".join(str(exc).split()))
        raise SystemExit(1)
