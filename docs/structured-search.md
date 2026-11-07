# Structured task search

`academic_search` currently uses SQLite and the fixture vocabulary. The PostgreSQL
port is not implemented. The current Search interface below is distinct from the
agreed database task-payload schema and the proposed integration.

## Reference revisions

Search reference: `f6f69f7e0dbf42de86610dead2e263c1261f35bd`, including
`academic_search/`, `tests/test_structured_search.py`,
`tests/test_search_fixtures.py`, and `fixtures/search/`.

Database reference: `7aa63cfc5453a70a12b73b099c4f56e1dc583825`, verified as the
remote branch tip on 2026-11-07. The agreed payload contract is
[`Database/task_schema.json`](https://github.com/Loser-r-6663/Smart-Calender-for-FITHCMUS/blob/7aa63cfc5453a70a12b73b099c4f56e1dc583825/Database/task_schema.json).
Files were reviewed at that immutable revision; this does not verify a deployed
database or subsequent branch changes. The local `origin/Database` is stale.

The selected interface is
[`Database/DatabaseManager.py`](https://github.com/Loser-r-6663/Smart-Calender-for-FITHCMUS/blob/7aa63cfc5453a70a12b73b099c4f56e1dc583825/Database/DatabaseManager.py).
Its dependencies inspected at the same revision are `Database/db_config.py`,
`tasks.py`, `daily_task_objects.py`, `task_objects.py`, `task_validation.py`,
`task_config.py`, and `enums.py`; the schema reference is `Database/Db_query.sql`,
alongside the agreed JSON Schema above.
Database files are absent from this Search checkout. The separate lowercase
`Database/database_manager.py` is not the selected interface, even though the
Database module guide recommends it for new code. Its transaction and return
contracts must not be attributed to the selected module.

## Current Search usage

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

## Current SQLite public interface

This example consumes the existing fixtures; its task dictionaries are not valid
current database payloads. See the database contract and fixture gaps below.

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
  hyphens. This is narrower than the Database contract described below.
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

Filters are query operators, not task-payload properties. For example,
`min_training_points` and `max_training_points` constrain `training_points`;
`types` selects task `type` values. They do not belong in `task_schema.json`.

| Filter | Accepted value and semantics |
| --- | --- |
| `types` | List from `class`, `assignment`, `exam`, `event`, `personal`, `tuition`; omitted means all six types |
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

## SQLite adapter and tests

`fixture_adapter.create_demo_database(tasks)` builds an isolated in-memory
`search_tasks` table with the original JSON `payload` and filter/sort columns.
`store_task(connection, task)` updates both together without committing. Reads
reflect edits, cancellation and deletion visible to that connection. The adapter
validates the projection, not the complete database payload contract.

The tests exercise nine structured fixture expectations plus boundaries,
sorting, pagination, validation and update/delete visibility. Keyword, hybrid
and semantic requests remain unsupported. These tests do not verify PostgreSQL
integration. Dataset details and compatibility gaps belong in the
[fixture README](../fixtures/search/README.md#dataset-contract-and-database-compatibility).

## Current database task-payload contract

`Database/task_schema.json` declares a Draft 2020-12 object with 21 permitted
properties and `additionalProperties: false`. Only `id`, `title`, and `type` are
unconditionally required. Assignment and tuition additionally require a non-null
`deadline`. Optional does not imply nullable: explicit null is allowed only where
listed below. JSON Schema defaults are annotations; validation alone does not
insert them. Python `TaskData` / `task_config.py` supplies the runtime defaults.

| Task field(s) | Payload type, constraints and default when omitted |
| --- | --- |
| `id` | Required string, 1–64 characters, containing a non-whitespace character; no lowercase or UUID-only restriction |
| `title` | Required string, 2–255 characters, containing a non-whitespace character |
| `type` | Required string: `class`, `assignment`, `exam`, `event`, `personal`, `tuition`; no schema default |
| `course`, `target_audience`, `location` | String or null; strings have minimum length 1 and no schema maximum; default null. `course` is free text, not a validated course code |
| `description` | String or null; default null |
| `registration_start`, `registration_end`, `start_time`, `end_time`, `deadline` | `date-time` string or null, default null; `deadline` cannot be omitted/null for assignment or tuition |
| `estimated_hours` | Number or null, inclusive 0.25–40; default null |
| `training_points` | Integer 0–100, non-null; default 0 |
| `drl_category` | `dieu_1`, `dieu_2`, `dieu_3`, `dieu_4`, `dieu_5`, or null; default null, subject to the positive-points discrepancy below |
| `recurrence` | String or null, maximum 50 characters; `T2`–`T7` or `CN`, one space, then `HH:MM-HH:MM` in 24-hour time, e.g. `T2 08:00-10:00`; default null |
| `status` | `active`, `done`, `archived`, `cancelled`; non-null, default `active` |
| `is_manual` | Boolean, non-null; default false |
| `source_url` | URI string beginning with `http://` or `https://`, or null; default null |
| `source_platform` | `moodle`, `portal`, `facebook`, `custom`; non-null, default `custom` |
| `updated_at` | Non-null `date-time` string when supplied; optional, with current UTC time described in the schema and generated by Python/SQL |

Neither `course_code` nor `embedding` is permitted. Non-null timestamps require
an explicit timezone offset (or `Z`); Python accepts aware `datetime` objects as
well as strings, and SQL uses `TIMESTAMPTZ`. Known registration/event endpoints
must be ordered strictly, and recurrence start must precede end. JSON Schema
records these cross-field rules in `x-validation-rules`, which are descriptive,
not standard validation assertions; enable format checking for `date-time`/`uri`.

### Discrepancies requiring Database confirmation

| Area | JSON Schema versus implementation | Decision and effect |
| --- | --- | --- |
| Positive points/category | The conditional permits omitted `drl_category` but rejects explicit null when points > 0. Its annotation and Python instead assign `dieu_3` for either omission or null. SQL requires a category for positive points and supplies no category default | Database teammate must confirm null rejection versus normalization; raw schema validation and Python acceptance currently differ |
| Text normalization | JSON Schema checks raw lengths and `\S` on ID/title; Python strips text and rejects NUL. Whitespace-only `course`, audience or location can pass JSON Schema; Python rejects them after stripping. SQL uses a `btrim` space check for course/ID/title, permits empty audience/location and retains surrounding spaces | Database/ingestion teammates must confirm normalization and direct-writer rules before lookup/round-trip parity is promised |
| Recurrence and intervals | JSON Schema's recurrence regex checks syntax but not start < end; interval ordering is also an annotation. Python enforces both. SQL enforces registration/event ordering but only recurrence length | Database teammate must confirm where these payload rules are enforced for every writer; schema-only validation is insufficient |
| Timestamp input | JSON `date-time` needs format checking; Python explicitly rejects naive datetimes. PostgreSQL can accept naive timestamp input and interpret it in the session timezone | Database teammate must confirm that all ingestion paths enforce aware input before SQL; storage type alone does not validate the payload rule |
| URL validation | JSON Schema uses URI format plus an HTTP(S) prefix; Python uses `AnyHttpUrl` and may normalize URLs. SQL stores unrestricted nullable text | Database teammate must confirm shared URL acceptance/normalization; direct SQL is not payload validation |
| Numeric input | JSON Schema allows integral numbers such as `1.0` for an integer field; Python declares `training_points` as a strict integer and rejects a decoded float | Database/API teammates must confirm consistent payload validation/coercion across entry points |
| Required creation input | JSON Schema/`TaskData` require `id` and `type`; selected manager creates a UUID (overriding an input ID) and supplies `personal` when type is omitted | Database/API teammates must distinguish manager convenience inputs from schema-valid complete task payloads |

## Verified PostgreSQL interface and limitations

`from Database.DatabaseManager import DatabaseManager` selects the agreed module.
Construction connects immediately using `psycopg2.connect`; explicit constructor
settings override `get_database_config()` from `Database/db_config.py` (dotenv /
`DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT`). The singleton exposes
the live psycopg2 connection as `manager.connection`. Later construction reuses
the initialized instance, ignoring new settings. There is no connection pool,
borrow/transaction context, closed-connection recovery, structured-search method,
or exact-task getter on this class. Closing does not reset its initialized flag.

| Selected manager operation | Actual return / failure behavior |
| --- | --- |
| `create_task(user_id, task_data, work_date)` | Generates a UUID string and returns it; `None` on caught non-`ValueError` failures; `ValueError` (including Pydantic validation) is re-raised after rollback |
| `get_tasks_by_date(user_id, work_date)` | `list[DailyTaskObject]`, not dictionaries or JSON; each object extends `TaskObject` / `TaskData` with `work_date: date` and `is_completed_today: bool`; Pydantic `ValidationError` propagates, other caught query/conversion failures return `[]` |
| `update_task(task_id, update_data)` | Boolean; `False` for empty updates, absent task, or caught non-`ValueError` failure; `ValueError` is re-raised after rollback |
| `delete_task(task_id)` | Boolean; successful SQL returns `True` even if no row existed; caught failures return `False` |
| `connect()`, `close()`, context exit | No task result; connection errors re-raise; `close()` catches/logs errors |

`get_tasks_by_date` joins `tasks`, `user_tasks`, and `daily_tasks`, filters by user
and calendar date, and has no status predicate or stable ordering. It is not a
general search: it excludes tasks without the requested assignment/day links,
and has no deadline, interval, points, sorting or pagination contract. Its
failure-to-empty behavior cannot support Search's distinct failure outcome.
Cursor creation occurs before its try block, so some failures can still escape.
It closes its cursor but does not commit or roll back the read transaction.

Writes on the selected manager commit on success and roll back on caught errors.
`close()` commits pending work before closing; `__exit__` calls it even when the
context body raises. It is not a rollback-on-error context manager. A failed read
can leave the shared connection in an aborted transaction until rolled back.
These behaviors make ownership and concurrent use material integration limits.

The underlying `TaskRepository.get_by_id(connection, task_id)` returns
`dict[str, Any] | None` using `RealDictCursor`; it is not a method of the selected
manager. Repository create/update return row dictionaries and do not manage
transactions themselves. psycopg2 timestamp values are aware Python `datetime`
objects. Pydantic objects offer `model_dump()` (Python values) and
`model_dump(mode="json")` (JSON-compatible values); neither means the manager
returns JSON text.

## Proposed PostgreSQL Search contract (not implemented)

### Connection and transaction ownership

The application obtains the singleton via the selected `DatabaseManager` and
passes `manager.connection` into the future PostgreSQL Search adapter. Search
borrows that connection and owns only its cursors, closing each cursor on success
or failure. It must not open a parallel SQLite database, instantiate the lowercase
manager, or use `get_tasks_by_date` as a search substitute.

The application/Database integration owner owns connection lifetime and transaction
boundaries: commit successful units of work, roll back failed units (including
failed reads), and close the manager at application shutdown after resolving any
pending transaction. Search performs SELECTs only, never commits, rolls back a
caller's unrelated work, or closes the shared connection. Errors propagate so
the owner can roll back before reuse. PostgreSQL SELECTs can start transactions;
the owner must also end successful read transactions. Do not wrap each Search
call in `with DatabaseManager()` since context exit closes the shared singleton
and commits even on exceptions. Serializing access and arranging safe shutdown
require the ownership decision below; no automatic reconnect or retry is promised.

### Read projection and returned records

Query PostgreSQL `tasks` directly, selecting an explicit field list. There is no
production `search_tasks` table or JSON `payload` requirement.

| Current SQLite projection / JSON | PostgreSQL mapping and proposed Search output |
| --- | --- |
| `id`, `type`, `source_platform`, `status`, `training_points`, `target_audience`, `location` | Same named `tasks` columns; preserve stored values and nulls, subject to the points limitation below |
| `course_code` in both projection and payload | `tasks.course TEXT NULL`; output key `course`, with no inferred code alias |
| Six integer UTC-microsecond columns: `deadline`, `registration_start`, `registration_end`, `start_time`, `end_time`, `updated_at` | Same named `TIMESTAMPTZ` columns; output aware datetimes, nullable except `updated_at` |
| Payload-only `title`, `description`, `estimated_hours`, `drl_category`, `recurrence`, `is_manual`, `source_url` | Same named typed columns; return these values directly, not a reconstructed fixture payload |
| Payload-only `embedding` | Removed from current schema and `TaskData`; omit from PostgreSQL Search records, do not fabricate a null column |
| No daily fields in a base task | Exclude `work_date` and `is_completed_today`; those belong to `DailyTaskObject`, not task status or the base Search record |

The proposed Python interface retains `get_task_by_id(task_id) -> dict | None`
and `search_tasks(request) -> list[dict]`. Both use the same 21 task fields above
(the old 22 fields with `course_code` renamed and `embedding` removed), including
all nullable keys. It returns independent dictionaries, not mixed Pydantic objects,
tuples, JSON strings, or write-operation booleans. Do not return `SELECT *` extras
as an accidental public contract. Modifying a result does not update storage.

At an API boundary, serialize aware datetimes to ISO 8601 UTC strings ending in
`Z`, preserving microsecond precision where present, and `None` to JSON `null`.
Database `TIMESTAMPTZ` preserves instants, not the original textual offset; the
SQLite promise to echo the original fixture timestamp string does not carry over.
This is a proposed serialization rule, not a claim that a Search HTTP endpoint
exists. A caller adapting a Pydantic result must deliberately convert it and apply
the same timestamp normalization.

### Filters, IDs, dates and SQL

Preserve the current request rules, six-type coverage, active status default,
all-status exact lookup, AND/OR composition, interval boundaries, missing-date
semantics, numeric bounds, sort allowlists, and pagination bounds. An omitted
`types` filter means all types; explicit types narrow results rather than selecting
a different table. No automatic overdue status transition or fallback is added.
The following differences require a PostgreSQL adapter rather than reusing the
SQLite compiler unchanged:

- **Course:** current Database validation strips surrounding whitespace and
  accepts any nonempty `course` text, or null; there is no code regex, foreign key,
  or canonical course identifier. Propose `filters.course` as exact, case-sensitive
  stored-text equality, with nonempty text validation and no legacy code regex.
  Such equality is not proof of course identity: `CSC10004`, a course name, and a
  combined code/name may refer to the same course but differ as stored strings.
  Retaining `filters.course_code` as an exact identifier requires the course
  decision below, not an automatic SQL rename. The current SQLite API still
  accepts only `course_code` and rejects `course`.
- **Task IDs:** Database `TaskData` strips surrounding whitespace, rejects NUL,
  and accepts a nonempty string of at most 64 characters with a non-whitespace
  character. The SQL column is `VARCHAR(64)` with a nonblank check, not UUID-typed.
  The manager generates UUIDs on creation, but repository inputs are not limited
  to UUIDs: uppercase, underscores, Unicode and internal spaces can be accepted.
  Propose string validation consistent with the model (strip, reject NUL, require
  1–64 characters and a non-whitespace character), then exact bound equality;
  do not retain the fixture regex or require UUID parsing. Quotes and SQL-looking
  text within these constraints are data, not automatically invalid syntax.
  SQL-only writers can retain surrounding spaces that model writers strip;
  canonicalization of such legacy IDs requires the decision below.
- **Time:** keep the current aware ISO request syntax and validation. Parse into
  timezone-aware Python `datetime` parameters (optionally normalized to UTC) and
  bind them through psycopg2 against `TIMESTAMPTZ`; do not send SQLite integer
  microseconds or compare timestamp text. Reject naive/date-only timestamps,
  invalid or incomplete ranges and `start >= end` before SQL. Equivalent offsets
  denote the same instant. Callers calculating “today” use Asia/Ho_Chi_Minh day
  boundaries with explicit offsets; storage/session timezone must not redefine
  those boundaries. Deadline, registration bounds, event interval and update
  timestamps remain independent. `TaskRepository.update` sets `updated_at` to
  current UTC; it is not an event date or daily `work_date`. Database validators
  and constraints require ordered known intervals and assignment/tuition deadlines.
  Missing endpoints remain independently nullable. Recurrence text does not
  expand into occurrences during Search.
- **SQL:** bind all values with psycopg2 `%s` parameters, including lists' members,
  timestamps, prefix text, limit and offset. Build only allowlisted identifiers
  and directions into SQL. Preserve literal case-sensitive prefix behavior using
  `left(location, char_length(%s)) = %s` with the prefix bound twice, under an
  explicitly deterministic case-sensitive text collation (for example `"C"`).
  `%`, `_`, quotes and backslashes remain literal. Apply the same explicit text
  comparison policy to exact text filters and ID sorting. Do not interpolate
  values or silently switch to `ILIKE`/wildcard matching.
- **Ordering:** default `deadline ASC NULLS LAST, id ASC`; other nullable sorts
  also use `NULLS LAST` in both directions and ascending ID as final tie-breaker.
  ID-only sort follows the requested direction. Define text ID order with the
  deterministic collation above, avoiding database-locale-dependent pagination.
  Apply WHERE and ordering before bound LIMIT/OFFSET. Stable pages assume unchanged
  data; the owner supplies an appropriate snapshot transaction when required.
  If user/source links are later queried, use `EXISTS` or deduplicate before
  pagination so a task appears once.
- **Outcomes:** invalid requests raise `SearchValidationError` before SQL; valid
  empty structured results are `[]`, absent exact IDs are `None`. Database/query
  failures propagate as psycopg2 errors (connection configuration failures also
  remain errors), with transaction cleanup owned above. Never route Search
  through the selected manager's caught-failure `[]`/`False`/`None` conventions.

All `*_within` predicates stay `[start, end)`. Registration-open keeps inclusive
closing (`registration_start <= at <= registration_end`) and requires both bounds.
Overlap requires both endpoints and `start_time < end_time`,
`start_time < query_end AND end_time > query_start`; touching boundaries do not
match. Starts-within needs only a known start. SQL null comparisons exclude unknown
dates only from predicates on those dates; do not coalesce missing dates into
deadlines, infinities, or update times.

### Training points and fixture compatibility

The SQLite adapter/test suite distinguishes known zero from unknown (`None`).
Unknown fails either numeric bound, including a bound of zero, but remains
eligible without a points predicate. The base JSON dataset uses integers;
`test_points_inclusive_bounds_and_unknown` adds null-point variants explicitly.

Current PostgreSQL `training_points INT NOT NULL DEFAULT 0` and strict integer
`TaskData` validation support only numeric values 0–100. Omission becomes
zero; explicit null is rejected. No existing flag distinguishes unknown from
zero. Search cannot recover that distinction or reinterpret every stored zero as
unknown. Positive points require a category at SQL level; validation supplies
`dieu_3` for an omitted or null category, unlike the JSON Schema null rule above.
Whether absent information should mean zero or unknown is a
business-policy conflict requiring confirmation, not a Search conversion rule.

JSON fixtures remain test data. Production searches read PostgreSQL directly,
with no JSON-to-SQLite import. The existing fixtures require explicit field,
recurrence and request mappings for future PostgreSQL tests; see the
[fixture compatibility table](../fixtures/search/README.md#dataset-contract-and-database-compatibility).
The current demo and tests retain their existing request/response contract.

## Unresolved team decisions

Owners below identify the teammate roles that must confirm each decision; no
individual assignment or approval is recorded in the inspected sources.

| Decision requiring confirmation | Effect on implementation | Teammate responsible for confirmation |
| --- | --- | --- |
| Canonical course identity and legacy `course_code` requests: exact stored text, authoritative code mapping, or a separate identifier? | Blocks promising code isolation for arbitrary `course` text and finalizing alias/rejection rules; no substring or inferred name-to-code conversion | Database teammate with Parser/crawler teammate; Search teammate confirms request compatibility |
| Does missing training-point information mean zero, or must unknown be represented separately? | Current schema/model cannot preserve the SQLite null distinction; either revise that policy or agree a Database representation before claiming parity; no automatic null-to-zero conversion | Database teammate with the teammate owning training-point/scheduling policy; Search teammate confirms filter expectations |
| Application owner of shared singleton transactions, serialization and shutdown, including safe rollback and reuse after failure/close | Proposed borrowing contract needs a safe caller; current manager lacks a transaction/borrow API and commits on context exit, so isolated concurrent Search use cannot be assumed | Database teammate with application integration teammate |
| Is Search over all `tasks`, or restricted to the authenticated user's assigned tasks? | Proposed direct-table query spans all tasks; user scoping needs an explicit trusted context and `EXISTS` on `user_tasks`, not an accidental date join or a user-supplied bypass | Application/API teammate with Database teammate; Search teammate confirms scope |
| Are IDs written outside model validation canonicalized consistently? | Proposed model-compatible trimming cannot retrieve a distinct SQL-only ID with surrounding spaces; confirm data policy before promising lookup parity for such rows | Database teammate with ingestion teammate |
