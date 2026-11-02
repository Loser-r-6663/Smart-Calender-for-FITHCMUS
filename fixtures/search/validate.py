"""Fixture integrity checks, not a production search implementation or adapter."""
import copy
import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
CLOCK = "2026-10-30T12:00:00+07:00"
TYPES = {"class", "assignment", "exam", "event", "personal", "tuition"}
STATUSES = {"active", "done", "archived", "cancelled"}
SOURCES = {"moodle", "portal", "facebook", "custom"}
DATES = {"registration_start", "registration_end", "start_time", "end_time", "deadline", "updated_at"}
FIELDS = DATES | {"id", "title", "type", "course_code", "description", "target_audience",
                  "location", "estimated_hours", "training_points", "drl_category", "recurrence",
                  "status", "is_manual", "source_url", "source_platform", "embedding"}
FILTERS = {"course_code", "types", "statuses", "source_platform", "target_audience",
           "location_prefix", "min_training_points", "registration_open_at",
           "registration_end_within", "deadline_within", "start_time_within", "event_overlaps"}
REQUIRED_TAGS = {"course-isolation", "accent-equivalence", "closes-today", "before-exact-after",
                 "overlap", "starts-within", "missing-start", "missing-end", "missing-both",
                 "status-default", "status-cancelled", "status-done", "negative", "update-title",
                 "update-deadline", "cancel-operation", "delete-operation", "semantic"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def timestamp(value):
    require(isinstance(value, str) and "T" in value, f"Invalid timestamp: {value!r}")
    parsed = datetime.fromisoformat(value)
    require(parsed.utcoffset() == timedelta(hours=7), f"Expected explicit UTC+07:00: {value}")
    return parsed


def normalize(text):
    folded = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    return re.findall(r"[a-z0-9]+", "".join(c for c in folded if not unicodedata.combining(c)))


def validate_task(task):
    require(set(task) == FIELDS, f"Task fields differ: {task.get('id')}")
    require(isinstance(task["id"], str) and re.fullmatch(r"[a-z0-9-]{1,40}", task["id"]), "Invalid task ID")
    require(isinstance(task["title"], str) and 2 <= len(task["title"]) <= 255, "Invalid title")
    require(task["type"] in TYPES and task["status"] in STATUSES and task["source_platform"] in SOURCES, "Invalid task enum")
    require(type(task["is_manual"]) is bool, "is_manual must be boolean")
    require(task["course_code"] is None or re.fullmatch(r"[A-Z]{3}\d{5}", task["course_code"]), "Invalid course code")
    for key in ("description", "target_audience", "location", "recurrence"):
        require(task[key] is None or isinstance(task[key], str), f"Invalid {key}")
    for key in DATES:
        if task[key] is not None:
            timestamp(task[key])
    require(task["updated_at"] is not None and timestamp(task["updated_at"]) <= timestamp(CLOCK), "Invalid update clock")
    for start, end in (("start_time", "end_time"), ("registration_start", "registration_end")):
        if task[start] is not None and task[end] is not None:
            require(timestamp(task[start]) < timestamp(task[end]), f"Reversed interval: {task['id']}")
    if task["type"] in {"assignment", "tuition"}:
        require(task["deadline"] is not None, "Assignment/tuition needs its own deadline")
        require(task["registration_start"] is None and task["registration_end"] is None, "Do not overload registration dates")
    points = task["training_points"]
    require(type(points) is int and 0 <= points <= 100, "Invalid points")
    require(task["drl_category"] is None or task["drl_category"] in {f"dieu_{i}" for i in range(1, 6)}, "Invalid DRL category")
    require(not points or task["drl_category"] is not None, "Points need a category")
    hours = task["estimated_hours"]
    require(hours is None or (type(hours) in {int, float} and 0.25 <= hours <= 40), "Invalid estimated hours")
    require(task["embedding"] is None, "Embeddings are outside fixture scope")
    url = urlparse(task["source_url"])
    require(url.scheme == "https" and url.netloc == "fixtures.example.invalid" and url.path == "/" + task["id"], "Source must be a synthetic reference")


def validate_filters(filters):
    require(isinstance(filters, dict) and set(filters) <= FILTERS, "Unknown filter")
    for key, value in filters.items():
        if key.endswith("_within") or key == "event_overlaps":
            require(isinstance(value, list) and len(value) == 2, "Range needs two endpoints")
            require(timestamp(value[0]) < timestamp(value[1]), "Invalid filter range")
        elif key == "registration_open_at":
            timestamp(value)
        elif key in {"types", "statuses"}:
            allowed = TYPES if key == "types" else STATUSES
            require(isinstance(value, list) and bool(value) and set(value) <= allowed and len(value) == len(set(value)), "Invalid enum filter")
        elif key == "min_training_points":
            require(type(value) is int and 0 <= value <= 100, "Invalid points filter")
        else:
            require(isinstance(value, str) and bool(value), "Invalid text filter")
            if key == "course_code":
                require(re.fullmatch(r"[A-Z]{3}\d{5}", value), "Invalid course filter")
            if key == "source_platform":
                require(value in SOURCES, "Invalid source filter")


def eligible(task, filters):
    """Audit explicit fixture predicates independently of any future search engine."""
    if task["status"] not in filters.get("statuses", ["active"]):
        return False
    for key in ("course_code", "source_platform", "target_audience"):
        if key in filters and task[key] != filters[key]:
            return False
    if "types" in filters and task["type"] not in filters["types"]:
        return False
    if "location_prefix" in filters and not (task["location"] or "").startswith(filters["location_prefix"]):
        return False
    if "min_training_points" in filters and task["training_points"] < filters["min_training_points"]:
        return False
    if "registration_open_at" in filters:
        start, end = task["registration_start"], task["registration_end"]
        if start is None or end is None or not timestamp(start) <= timestamp(filters["registration_open_at"]) <= timestamp(end):
            return False
    for field in ("registration_end", "deadline", "start_time"):
        key = field + "_within"
        if key in filters:
            lo, hi = map(timestamp, filters[key])
            if task[field] is None or not lo <= timestamp(task[field]) < hi:
                return False
    if "event_overlaps" in filters:
        lo, hi = map(timestamp, filters["event_overlaps"])
        start, end = task["start_time"], task["end_time"]
        if start is None or end is None or not (timestamp(start) < hi and timestamp(end) > lo):
            return False
    return True


def keyword_matches(task, keyword):
    tokens = set(normalize(" ".join(task[key] or "" for key in ("title", "description", "target_audience", "location"))))
    query_tokens = normalize(keyword)
    return bool(query_tokens) and set(query_tokens) <= tokens


def load():
    return tuple(json.loads((ROOT / f"{name}.json").read_text(encoding="utf-8")) for name in ("tasks", "queries", "scenarios"))


def validate(tasks, queries, scenarios):
    require(30 <= len(tasks) <= 50 and 25 <= len(queries) <= 40, "Counts outside requested ranges")
    for rows in (tasks, queries, scenarios):
        require(len({row["id"] for row in rows}) == len(rows), "Duplicate ID")
    for task in tasks:
        validate_task(task)
    base = {task["id"]: task for task in tasks}
    states = {"base": base}
    by_query = {query["id"]: query for query in queries}
    require(len(scenarios) == 3, "Need isolated edit, cancellation and deletion scenarios")
    for scenario in scenarios:
        require(scenario["id"] != "base" and scenario["from_state"] == "base", "Scenario must fork base")
        timestamp(scenario["reference_time"])
        require(scenario["reference_time"] == CLOCK, "Unexpected scenario clock")
        target = scenario["task_id"]
        require(target in base, "Unknown scenario target")
        state = copy.deepcopy(base)
        if scenario["operation"] == "update":
            changes = scenario["changes"]
            require(bool(changes) and "id" not in changes and set(changes) <= FIELDS, "Update must preserve identity")
            require(changes.get("updated_at") == scenario["reference_time"] and timestamp(base[target]["updated_at"]) < timestamp(changes["updated_at"]), "Update needs a newer timestamp")
            state[target].update(changes)
            validate_task(state[target])
            require(len(state) == len(base), "Update changed task count")
        else:
            require(scenario["operation"] == "delete" and "changes" not in scenario, "Unknown operation")
            del state[target]
            require(len(state) == len(base) - 1, "Deletion must remove one task")
        require(all(state[k] == v for k, v in base.items() if k != target), "Scenario touched unrelated work")
        states[scenario["id"]] = state
        for side, expected_state in (("before_queries", "base"), ("after_queries", scenario["id"])):
            require(bool(scenario[side]), "Scenario needs before and after expectations")
            for query_id in scenario[side]:
                require(query_id in by_query and by_query[query_id]["state"] == expected_state, "Scenario query has wrong state")
        require(any(target in by_query[q].get("expected_ids", []) for q in scenario["before_queries"]), "Before state must expose target")
    tags = set()
    for query in queries:
        qid = query["id"]
        require(re.fullmatch(r"q\d{2}", qid), "Invalid query ID")
        for key in ("text", "rationale"):
            require(isinstance(query[key], str) and bool(query[key].strip()), f"Missing {key}: {qid}")
        require(query["mode"] in {"structured", "keyword", "semantic", "hybrid"}, "Invalid mode")
        require(query["evaluation"] == "retrieval" and query["ordering_required"] is False, "Unexpected evaluation contract")
        timestamp(query["reference_time"])
        require(query["state"] in states, "Unknown query state")
        request = query["request"]
        require(set(request) <= {"filters", "keyword", "semantic_text"} and "filters" in request, "Unknown request field")
        filters = request["filters"]
        validate_filters(filters)
        if "registration_open_at" in filters:
            require(filters["registration_open_at"] == query["reference_time"], "Registration clock mismatch")
        require(("keyword" in request) == (query["mode"] in {"keyword", "hybrid"}), "Keyword mode mismatch")
        require(("semantic_text" in request) == (query["mode"] == "semantic"), "Semantic mode mismatch")
        state = states[query["state"]]
        require(bool(query["coverage_tags"]) and all(isinstance(t, str) and t for t in query["coverage_tags"]), "Invalid coverage tags")
        tags.update(query["coverage_tags"])
        require(len(query["excluded_ids"]) == len(set(query["excluded_ids"])) and set(query["excluded_ids"]) <= base.keys(), "Invalid exclusions")
        if "expected_ids" in query:
            require("relevance_labels" not in query, "Ambiguous expectation type")
            expected = query["expected_ids"]
            require(len(expected) == len(set(expected)) and set(expected) <= state.keys(), f"Unknown/duplicate expected ID: {qid}")
            # This audits the hand-written sets; it never writes or generates them.
            audited = {id for id, task in state.items() if eligible(task, filters) and ("keyword" not in request or keyword_matches(task, request["keyword"]))}
            require(set(expected) == audited, f"Expectation mismatch {qid}: missing={audited - set(expected)}, extra={set(expected) - audited}")
            positives = set(expected)
        else:
            require(query["mode"] == "semantic" and query["unlisted_eligible_grade"] == 0, "Invalid relevance policy")
            labels = query["relevance_labels"]
            require(bool(labels) and set(labels) <= state.keys(), "Unknown relevance ID")
            require(all(type(grade) is int and grade in {0, 1, 2} for grade in labels.values()), "Invalid relevance grade")
            require(all(eligible(state[id], filters) for id in labels), "Relevance label violates hard filter")
            positives = {id for id, grade in labels.items() if grade > 0}
        require(not positives.intersection(query["excluded_ids"]), "Expected/excluded conflict")
    require(REQUIRED_TAGS <= tags, f"Missing coverage: {REQUIRED_TAGS - tags}")
    require(by_query["q03"]["expected_ids"] == by_query["q04"]["expected_ids"] and normalize(by_query["q03"]["request"]["keyword"]) == normalize(by_query["q04"]["request"]["keyword"]), "Accent pair differs")
    require(base["evt-missing-start"]["registration_start"] is None and base["evt-missing-start"]["registration_end"] is not None, "Missing-start sentinel")
    require(base["evt-missing-end"]["registration_end"] is None and base["evt-missing-end"]["registration_start"] is not None, "Missing-end sentinel")
    require(base["evt-missing-both"]["registration_start"] is None and base["evt-missing-both"]["registration_end"] is None, "Missing-both sentinel")
    require(timestamp(base["evt-reg-before"]["registration_end"]) < timestamp(CLOCK) == timestamp(base["evt-reg-exact"]["registration_end"]) < timestamp(base["evt-reg-after"]["registration_end"]), "Closing boundary sentinels")
    require(base["evt-overlap"]["start_time"][:10] == "2026-10-29" and base["evt-overlap"]["end_time"][:10] == "2026-10-31", "Spanning event sentinel")
    edited = states["edited"]["asg-update"]
    require(edited["title"] != base["asg-update"]["title"] and edited["deadline"] != base["asg-update"]["deadline"], "Need title and deadline edit")
    require(states["cancelled"]["evt-cancel"]["status"] == "cancelled" and "evt-delete" not in states["deleted"], "Need cancellation and deletion")
    return f"Validated {len(tasks)} tasks, {len(queries)} queries, {len(scenarios)} scenarios; retrieval behavior not verified."


if __name__ == "__main__":
    print(validate(*load()))
