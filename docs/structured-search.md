# Structured task search

`academic_search` provides a UI-independent SQL search service and an isolated
SQLite fixture adapter. No production database access layer or executable Task
model exists on the inspected branch. The adapter is a test/demo integration
point based on the existing [22-field Task contract](../Suitable%20Schema%20for%20Task.md),
not a production migration or a new Task schema.

## Run

Use Python 3.10+ from the repository root; no third-party dependencies are needed:

```console
python -X utf8 -m academic_search.demo
python -X utf8 -m unittest discover -s tests -p test_structured_search.py -v
python -X utf8 -m unittest discover -s tests -v
python -X utf8 fixtures/search/build_data.py --check
python -X utf8 fixtures/search/validate.py
git diff --check
```

The demo always creates a fresh `:memory:` database and closes it on exit. It
does not open a real user database. Its seven examples show exact lookup,
course/type/status, due time, registration, event overlap, updated time, and an
empty result. All dates are fixed around the fixture reference clock
`2026-10-30T12:00:00+07:00`; no system clock is read.

## Public interface

```python
import json
from contextlib import closing
from pathlib import Path
from academic_search import SearchService, SearchValidationError
from academic_search.fixture_adapter import create_demo_database

tasks = json.loads(Path("fixtures/search/tasks.json").read_text(encoding="utf-8"))
with closing(create_demo_database(tasks)) as connection:
    search = SearchService(connection)
    task = search.get_task_by_id("asg-csc10004-lab")
    assert task["course_code"] == "CSC10004"
    assert search.get_task_by_id("not-present") is None

    results = search.search_tasks({
        "filters": {
            "course_code": "CSC10004",
            "types": ["assignment"],
            "statuses": ["active"],
        },
        "sort": "deadline",
        "direction": "asc",
        "limit": 20,
        "offset": 0,
    })
    assert [t["id"] for t in results] == [
        "asg-overdue", "asg-csc10004-lab", "asg-csc10004-project"
    ]
```

- `SearchService(connection)` uses a caller-owned SQLite connection containing
  the read projection described below. The caller owns transactions and closing.
- `get_task_by_id(task_id)` returns the original task dictionary or `None`.
  This is exact lookup across **all statuses**, independent of search defaults.
  IDs follow the current fixture contract: 1–40 lowercase letters, digits or
  hyphens. Future production UUID/hash conventions should be reconciled at
  integration time, rather than changing the fixture contract implicitly.
- `search_tasks(request)` returns a list of task dictionaries, possibly `[]`.
  There is no fallback, total-count query, or hidden result cache.
- Invalid input raises `SearchValidationError` (a `ValueError` subclass).
  SQLite failures propagate as `sqlite3.Error`, including missing tables and
  closed connections; they are never disguised as an empty successful result.

Returned dictionaries preserve the original 22-field documents, Unicode,
timestamp strings and null values. Modifying a returned dictionary does not
update the database. Search does not create schemas, write records, or commit.

## Requests and filters

Only `filters`, `sort`, `direction`, `limit`, and `offset` are accepted at the
request's top level. Omitted `filters` means `{}`. Unknown fields, including
`keyword` and `semantic_text`, are rejected instead of silently ignored.

Different filter categories combine with **AND**. Values within each supported
list combine with **OR**. Lists must be nonempty and contain unique valid values;
an explicitly empty list is an error, unlike an omitted filter. Explicit null
filters are errors too.

| Filter | Accepted value and semantics |
| --- | --- |
| `types` | List from `class`, `assignment`, `exam`, `event`, `personal`, `tuition` |
| `course_code` | Exact `[A-Z]{3}[0-9]{5}` code; CSC10004 cannot match CSC10005 |
| `source_platform` | One of `moodle`, `portal`, `facebook`, `custom` |
| `source_platforms` | Nonempty list of the same source enums; OR within the list |
| `statuses` | List from `active`, `done`, `archived`, `cancelled`; defaults to `["active"]` |
| `min_training_points`, `max_training_points` | Inclusive integer bounds in 0–100; minimum must not exceed maximum |
| `deadline_within` | Two timestamps: actual assignment/tuition due-time range |
| `registration_open_at` | Timestamp at which both known registration bounds contain the instant |
| `registration_end_within` | Two timestamps: registration closing-date range, even if already closed |
| `start_time_within` | Two timestamps: event start falls within the range (`starts_within`) |
| `event_overlaps` | Two timestamps: event interval intersects the range (`overlaps`) |
| `updated_at_within` | Two timestamps: last-update range |
| `target_audience` | Exact case-sensitive text, 1–100 characters |
| `location_prefix` | Literal case-sensitive prefix, 1–100 characters; `%` and `_` are not wildcards |

If singular and plural source filters are both supplied they intersect through
AND. The current contract has one source per task, so the service queries one row
per task without joins. Source-list matching cannot duplicate a task. No separate
source relationship is invented. A future many-source backend must use `EXISTS`
or an equivalent deduplicated projection before ordering and pagination.

Explicit statuses replace the active default, permitting completed (`done`),
cancelled and archived results. Time passage never changes status automatically;
overdue active tasks remain visible. Unknown training points remain null, and
fail either numeric bound, including `min_training_points: 0`. They are not
converted to zero. Without a points filter they remain eligible.

## Time and missing values

Requests accept ISO 8601 timestamp strings with seconds, an explicit offset or
`Z`, and optional 1–6 fractional second digits. Date-only, naive timestamps,
invalid dates, equal range bounds and reversed ranges raise validation errors.
Every range requires both endpoints. Input timestamps may use different offsets;
they are normalized to exact integer UTC microseconds before storage/comparison.
This avoids lexical timestamp comparisons and floating-point rounding. Original
GMT+7 fixture timestamps are preserved in returned documents.

The existing fixture policies apply:

- Every date range is half-open `[start, end)`: `timestamp >= start AND timestamp < end`.
- Assignment/tuition `deadline`, registration times, event times and `updated_at`
  are distinct columns and predicates; none substitutes for another.
- Definitely-open registration requires both dates and
  `registration_start <= instant <= registration_end`. The exact closing instant
  is included. Missing either bound is unknown and does not match.
- An event overlaps when `event_start < query_end AND event_end > query_start`
  and its stored interval is nonempty. An event spanning yesterday through
  tomorrow matches today. An event ending exactly at today's start or starting
  exactly at tomorrow's start does not overlap today.
- Overlap requires both event endpoints. Starts-within requires only a known
  start, so an unknown end does not disqualify that separate predicate.
- Missing timestamps fail predicates on that field. Unrelated filters can still
  return the record. The adapter rejects equal/reversed known event or
  registration endpoints; it accepts independently missing optional endpoints.
  Zero-duration event representation is outside this interval contract.
- Recurrence expansion is not implemented; class records are materialized
  occurrences, as in the existing fixtures.

Example time request:

```python
request = {
    "filters": {
        "types": ["event"],
        "event_overlaps": [
            "2026-10-30T00:00:00+07:00",
            "2026-10-31T00:00:00+07:00",
        ],
    },
    "sort": "id",
}
# Result IDs: ["evt-overlap", "evt-today"]
```

## Sorting, pagination, and SQL

Default ordering is `deadline asc`, with null deadlines explicitly last and ID
ascending as the final tie-breaker. Sort options are `id`, `deadline`,
`start_time`, `updated_at`, and `training_points`; directions are `asc` and `desc`.
All nullable sort columns put unknown values last in both directions. Every
non-ID sort ends with ascending ID. ID sorting directly uses the chosen direction
and is already unique.

`limit` defaults to 20 and must be an integer from 1 to 100. `offset` defaults
to 0 and must be an integer from 0 to 100000. Booleans and numeric strings are
rejected. Filtering and ordering happen before SQL LIMIT/OFFSET. An offset past
the result count returns `[]`. Pagination is deterministic for an unchanged
database; callers needing a snapshot across concurrent writes own that transaction.

All user values, including timestamps, text, list members, limit and offset,
are bound parameters. Column names and order directions are selected from fixed
allowlists. A literal prefix uses `substr`, avoiding wildcard interpretation.
There are no speculative indexes or production migration changes.

## Adapter and remaining integration

`fixture_adapter.create_demo_database(tasks)` creates only an in-memory table
named `search_tasks`. It stores the original task as JSON in `payload`, plus a
small projection of columns needed for filtering/ordering: identity, type, course,
source, status, points, audience, location, and the six normalized date columns.
The primary key enforces one row per task. The adapter validates projected enums,
timestamps, intervals and points; it is not a complete production Task validator.

`fixture_adapter.store_task(connection, task)` inserts or updates the same ID,
updating payload and comparison columns in one statement. It does not commit.
The service reads database state on each call, so changes, cancellations and
explicit deletions are visible immediately to that connection. Write workflows,
authorization, crawler reconciliation and transaction ownership belong to the
future backend; this adapter is for tests and demos only.

Production integration still needs an agreed database/model layer and an adapter
or view supplying this normalized read projection. Schema ownership, durable
synchronization, many-source relationships, and performance evaluation remain
backend work. The tests verify SQL retrieval through the fixture-backed adapter,
not a production database, keyword retrieval, semantic search or natural-language
query understanding.

Tests consume all nine existing `mode: structured` exact expectations without
modification. Additional expectations are explicitly authored for filters,
boundaries, sorting, pagination, invalid requests and update/delete visibility.
Keyword/hybrid/semantic fixtures are not sent to this structured-only service;
their unsupported fields are rejected rather than dropped.
