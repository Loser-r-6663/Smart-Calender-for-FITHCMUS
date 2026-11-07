# Structured task search

`academic_search.SearchService` reads existing PostgreSQL `tasks` through the
shared connection exposed by `Database/DatabaseManager.py`. It never imports
fixtures, creates a database, or falls back to SQLite. All six task types are
eligible by default: `class`, `assignment`, `exam`, `event`, `personal`, `tuition`.

## Reference revisions

Search baseline: `f6f69f7e0dbf42de86610dead2e263c1261f35bd`, including
`academic_search/`, `tests/test_structured_search.py`,
`tests/test_search_fixtures.py`, and `fixtures/search/`.

Database reference: `7aa63cfc5453a70a12b73b099c4f56e1dc583825`, verified as the
remote branch tip on 2026-11-08. The agreed payload contract is
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

## PostgreSQL usage and configuration

The application supplies an initialized instance of the exact selected manager.
The Database package and its dependencies (`psycopg2-binary`, Pydantic v2,
`python-dotenv`) must be available in the integrated application's Python path.
They are not bundled in this Search-only checkout. Search adds no driver or
connection manager of its own; importing Search alone does not connect anywhere.

`Database/db_config.py` loads dotenv/environment settings: `DB_HOST` (default
`localhost`), `DB_NAME` (`task_manager_db`), `DB_USER` (`postgres`), `DB_PASSWORD`
(empty default), and `DB_PORT` (`5432`). Configure these for the intended database
without storing credentials in source. Selected-manager constructor arguments
`host`, `database`, `user`, `password`, `port` override those defaults on its first
initialization. Apply the team's schema separately; Search runs no migrations.

```python
from Database.DatabaseManager import DatabaseManager
from academic_search import SearchService


def read_for_user(manager, trusted_user_id, task_id):
    search = SearchService(manager, user_id=trusted_user_id)
    task = search.get_task_by_id(task_id)
    results = search.search_tasks({
        "filters": {"course": "Cấu trúc dữ liệu", "types": ["class", "assignment"]},
        "sort": "deadline",
        "limit": 20,
        "offset": 0,
    })
    return task, results


manager = DatabaseManager()
```

The caller resolves `trusted_user_id` from its authorized application context;
never take it directly from an untrusted search request. `user_id` must be a
positive PostgreSQL integer. Both methods use `EXISTS` on `user_tasks` for that
user, following the selected manager's user-linked read scope. They do not require
`daily_tasks` scheduling links and do not duplicate tasks with multiple links.
An existing task outside this scope returns the same `None` as an absent task.
There is no global or public-task bypass. The repository defines API role
permissions (admin can read; the LLM role can create), but no public/shared-task
visibility policy or end-user identity mapping. The application must retain its
permission checks; wider visibility needs team agreement.

## Interface and transaction ownership

- `SearchService(manager, user_id=...)` borrows the current `manager.connection`
  on each operation. It opens/closes only cursors. It never commits, rolls back,
  closes/reconnects the shared connection, writes data, or retries implicitly.
- `get_task_by_id(task_id)` normalizes IDs using the shared validator: strip outer
  whitespace, reject empty/NUL input, allow 1–64 characters, including uppercase,
  Unicode and internal spaces. It looks across **all statuses** within user scope
  and returns a task dictionary or `None`.
- `search_tasks(request)` returns a list of task dictionaries, possibly `[]`.
  Status defaults to active; omitted types do not restrict type.
- Invalid input raises `SearchValidationError` before database access. Database,
  cursor and row-conversion failures raise `SearchDatabaseError`, retaining the
  original exception in `__cause__`. A failed query never becomes `[]` or `None`.

The application owns transaction boundaries, successful read completion, rollback
on failure and final manager shutdown. PostgreSQL SELECTs can start transactions.
After `SearchDatabaseError`, the owner must roll back the failed unit of work
before reuse; Search cannot roll back unrelated pending writes. Serialize use of
the singleton connection and supply a suitable transaction snapshot when needed.
Do not use a manager context per Search call: its `close()` commits pending work
and its context exit closes even when the body raises. Resolve the transaction
before shutdown instead.

Results are independent dictionaries of exactly the 21 task fields below, with
nullable keys retained, Unicode and zero preserved, and aware Python `datetime`
values for non-null timestamps. No `course_code`, `embedding`, JSON `payload`,
`work_date`, or `is_completed_today` is returned. Editing a dictionary does not
write to storage. At an API boundary serialize datetimes to UTC ISO 8601 strings
ending in `Z`, preserving microseconds when present, and `None` as JSON `null`.
`TIMESTAMPTZ` preserves the instant, not the original input offset spelling;
Search itself returns Python values and does not implement an HTTP endpoint.

## Requests and filters

`academic_search/validation.py` validates requests without a database connection.
`validate_request()` returns an immutable `ValidatedRequest`: enum lists become
tuples, defaults are explicit, and timestamps become aware UTC `datetime` values.
It accepts free-text `course` and provides a database-compatible task-ID normalizer
(trim surrounding whitespace, reject NUL/empty values, maximum 64 characters).
It does not validate complete task payloads or execute queries.

`academic_search/postgres.py` compiles only validated requests into SQL with
psycopg2 `%s` parameters and maps database rows. It binds aware datetimes directly;
SQLite timestamp integers and JSON payload decoding are absent from this path.

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
| `course` | Exact case-sensitive stored text; nonblank string without NUL, no code regex or maximum length; not a canonical course identifier |
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
overdue active tasks remain visible. The current PostgreSQL schema stores integer
points 0–100 with default zero and rejects null; it cannot represent unknown points
separately. Search neither treats zero as unknown nor invents a replacement flag.
The isolated SQLite tests still cover nullable points; that is a compatibility gap,
not a representation supported by the current production schema.

## Time and missing values

Requests accept ISO 8601 timestamp strings with seconds, an explicit offset or
`Z`, and optional 1–6 fractional second digits. Date-only, naive timestamps,
invalid dates, equal range bounds and reversed ranges raise validation errors.
Every range requires both endpoints. Input timestamps may use different offsets;
they are normalized to aware UTC datetimes and bound directly against `TIMESTAMPTZ`.
No lexical comparison or floating-point timestamp conversion is used.

The same interval policies apply in PostgreSQL and the isolated fixture tests:

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
  return the record. Database Python validation and SQL constraints reject
  equal/reversed known event or registration endpoints and allow independently
  missing optional endpoints.
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
allowlists. Exact text filters and ID ordering use deterministic `COLLATE "C"`.
A literal prefix uses `left(location, char_length(%s)) = %s` under that collation,
with the prefix bound twice; `%`, `_`, quotes and backslashes remain literal.
User scoping and filtering precede ordering and LIMIT/OFFSET. No indexes or
migrations are added.

## SQLite adapter and tests

The legacy service is explicitly `academic_search.sqlite_service.SearchService`;
its connection-based constructor, `course_code` filter, 1–40 character fixture-ID
regex, fixture dictionaries and timestamp conversion remain unchanged. It is
not selected automatically by the production service. `academic_search.demo`
uses that explicit SQLite import. For the isolated demo and standard-library tests:

```console
python -X utf8 -m academic_search.demo
python -X utf8 -m unittest discover -s tests -v
python -X utf8 fixtures/search/build_data.py --check
python -X utf8 fixtures/search/validate.py
git diff --check
```

`fixture_adapter.create_demo_database(tasks)` builds an isolated in-memory
`search_tasks` table with the original JSON `payload` and filter/sort columns.
`store_task(connection, task)` updates both together without committing. Reads
reflect edits, cancellation and deletion visible to that connection. The adapter
validates the projection, not the complete database payload contract.

The tests exercise nine structured fixture expectations plus boundaries,
sorting, pagination, validation and update/delete visibility. Keyword, hybrid
and semantic requests remain unsupported. The PostgreSQL SQL/row/error/ownership
tests use mocks, so they do not verify execution on a PostgreSQL server. Dataset details and compatibility gaps belong in the
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

## Schema compatibility and verification limits

PostgreSQL selects `tasks` columns directly: projected SQLite columns map to the
same named database fields, except legacy `course_code` has no automatic mapping.
The old payload-only fields (title, description, hours, category, recurrence,
manual flag and source URL) are actual `tasks` columns. The six date fields use
`TIMESTAMPTZ`, and `embedding` is absent. No `search_tasks` table or payload is
required by production search.

`course_code` is rejected by PostgreSQL request validation. `course` is free-text
equality, with the supplied text preserved; a name, code and combined code/name
can denote the same course but not compare equal. Supporting legacy exact-code
requests needs an authoritative mapping or a separate identifier, confirmed by
the Database and Parser/crawler teammates. No substring or inferred-code fallback
is performed. Other existing structured filters are supported; their names are
query operators rather than missing task-schema fields.

The JSON fixtures remain unchanged test data. They contain forbidden database
properties and incompatible recurrence strings; see the
[fixture compatibility table](../fixtures/search/README.md#dataset-contract-and-database-compatibility).
The PostgreSQL path does not coerce or import them. Unknown training-point policy
still needs confirmation from the Database and training-point/scheduling teammates:
the schema cannot preserve the null-versus-zero distinction from SQLite tests.

## Dedicated PostgreSQL integration tests

`tests/test_postgres_search_integration.py` uses the real production SearchService,
the exact `Database/DatabaseManager.py`, its task repository and PostgreSQL. The
Database package/dependencies must be available on Python's import path. Provision
a dedicated database ending in `_search_test` (for example `calendar_search_test`)
and a test role with CONNECT and CREATE-schema privileges. Never point this suite
at a shared development or production database.

Set `SEARCH_TEST_DB_PASSWORD` privately in the process environment, then configure:

```powershell
$env:RUN_SEARCH_POSTGRES_INTEGRATION = "1"
$env:SEARCH_TEST_DB_HOST = "localhost"
$env:SEARCH_TEST_DB_NAME = "calendar_search_test"
$env:SEARCH_TEST_DB_USER = "search_tester"
$env:SEARCH_TEST_DB_PORT = "5432"
$env:SEARCH_TEST_DB_CONFIRM = $env:SEARCH_TEST_DB_NAME
python -X utf8 -m unittest discover -s tests -p test_postgres_search_integration.py -v
python -X utf8 -m unittest discover -s tests -p test_postgres_search_integration.py -v
```

All six `SEARCH_TEST_DB_*` values are required. Normal `DB_*` settings, dotenv
values and the former `SEARCH_TEST_USER_ID`/`SEARCH_TEST_TASK_ID` are not used as
test targets. Without opt-in, integration cases explicitly skip. With opt-in,
missing/invalid settings, dependencies, source fingerprints or connectivity are
setup errors, never successful integration results. Each invocation must use a
fresh Python process: the suite refuses an existing manager singleton because its
constructor ignores new connection settings after initialization.

Before any DDL/data writes, the suite checks the database-name suffix and explicit
confirmation, then verifies `current_database()`, `session_user`, host and port on
the connected manager. It checks normalized source fingerprints for the reviewed
`Db_query.sql`, `DatabaseManager.py` and `tasks.py` at Database revision
`7aa63cfc5453a70a12b73b099c4f56e1dc583825`. Source drift requires reviewing those
files and updating the test fingerprints; do not bypass the guard.

Each case creates its own `search_it_<uuid>` schema and sets a search path containing
only that schema and `pg_catalog`, excluding `public`. It runs the team's existing
`Database/Db_query.sql` unchanged there, creates two test users, validates/inserts
adapted fixture tasks through `TaskRepository.create`, and assigns base tasks only
to the first user. Calendar links are created by selected-manager creation tests;
normal search must also work without them. No database is created, no application
schema is migrated, and no shared tables are cleared.

Cleanup is registered before initialization/seeding. It rolls back pending/failed
work, revalidates the target, and drops only the exact schema created by that case,
then commits cleanup and verifies the schema is absent from `pg_namespace`.
This removes rows even when manager writes committed them;
transaction rollback alone would not suffice. The suite owns and closes its test
connection after all cases. Cleanup failures fail the suite. An abruptly killed
process may leave its uniquely named scratch schema; inspect that exact schema
in the dedicated database before removing it, rather than sweeping other schemas.
The second command above verifies repeatability and committed-write cleanup when
a dedicated database is available.

The test-only adapter in `tests/postgres_search_support.py` preserves fixture IDs,
points and authored expected IDs. It maps controlled `course_code` values and
filters to identical `course` text, omits null `embedding`, maps `NONE` to null and
`WEEKLY:FRI` to `T6 07:30-11:00`, and parses aware timestamps. This is not a
production course-identity mapping. Null training points are rejected by both
Python and SQL tests; the current schema supports no unknown-points value.
The nine original structured-query expectations remain unchanged. Mutation tests
assert the same title/deadline, cancellation and deletion purposes; updated-time
checks use a captured current-UTC window because repository updates generate
`updated_at` instead of preserving the fixture scenario clock.

The suite asserts exact IDs/order for lookup, all six types, combined filters,
statuses, course text, points, half-open dates, registration closing inclusivity,
missing dates, overlaps, equivalent offsets, microseconds, stable sorting,
null ordering, pagination and empty results. It verifies committed manager
update/cancel/create/delete visibility, owner isolation/shared assignments,
validation errors and real query failures with retained database-error causes.
It never mocks query execution or substitutes SQLite. Offline setup-guard and
fixture-adapter tests are separate and do not count as real PostgreSQL checks.

No dedicated target, Database runtime or PostgreSQL driver was available for live
verification on 2026-11-08. The suite is implemented but PostgreSQL execution and
two-run cleanup verification remain outstanding until that environment is supplied.

## Remaining integration decisions

| Decision | Effect | Teammate responsible for confirmation |
| --- | --- | --- |
| Public/shared or unassigned task visibility and trusted end-user identity | Current Search follows user-task links only; it cannot expose a broader pool or authenticate a user by itself | Database and application/API teammates |
| Canonical course identity / legacy exact-code requests | Cannot equate arbitrary `course` text with an exact course identifier | Database and Parser/crawler teammates |
| Unknown training points | Current non-null schema cannot preserve unknown independently from zero | Database and training-point/scheduling teammates |
| Singleton connection coordination and shutdown | Application must serialize use and own commit/rollback; current manager has no borrow/transaction API or automatic recovery | Database and application integration teammates |
| IDs written outside model normalization | Trimmed lookup cannot retrieve a distinct SQL-only ID with outer spaces | Database and ingestion teammates |

The schema/validator discrepancies listed above also need Database confirmation.
This Search-only checkout consumes an injected manager; the application must make
the reviewed `Database` package and its dependencies available at deployment.
