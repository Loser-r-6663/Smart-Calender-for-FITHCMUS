# Smart-Calender-for-FITHCMUS

- [Structured search service, demo, and tests](docs/structured-search.md)
- [Representative search fixtures and policies](fixtures/search/README.md)

## Local PostgreSQL search sample

Prerequisites: an available Docker engine with Compose v2, Python 3.10+, and
`psycopg2-binary` in the project environment. The sample uses a separate Compose
project, loopback-only port and persistent volume. No system PostgreSQL service
or team database is used. Run the commands below from the repository root.

Configure this PowerShell process explicitly. The password prompt does not echo
the password; do not put real credentials in source or shell command history.
`SEARCH_SAMPLE_DB_HOST`, `NAME`, `USER`, `PASSWORD`, `PORT`, and `CONFIRM` are all
required with the `SEARCH_SAMPLE_DB_` prefix. Application `DB_*` and test
`SEARCH_TEST_DB_*` settings are never used as fallbacks.

```powershell
$env:SEARCH_SAMPLE_DB_HOST = "127.0.0.1"
$env:SEARCH_SAMPLE_DB_NAME = "calendar_sample_search_test"
$env:SEARCH_SAMPLE_DB_USER = "search_sample"
$env:SEARCH_SAMPLE_DB_PORT = "55432"
$env:SEARCH_SAMPLE_DB_CONFIRM = $env:SEARCH_SAMPLE_DB_NAME
$env:SEARCH_SAMPLE_DB_PASSWORD = [System.Net.NetworkCredential]::new("", (Read-Host "Local sample password" -AsSecureString)).Password
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install psycopg2-binary
docker compose -f compose.search-sample.yml up -d --wait
.\.venv\Scripts\python.exe -X utf8 -m search_sample seed
.\.venv\Scripts\python.exe -X utf8 -m search_sample seed
.\.venv\Scripts\python.exe -X utf8 -m search_sample demo
```

The dedicated database name must end in `_search_test`, confirmation must match
it exactly, and the host must be loopback. The tool verifies the connected
database, session user, host and port before seed/reset. Missing configuration or
driver is an explicit error. Existing credentials/data in a Compose volume are
not changed by environment settings on later starts; keep the original local
settings when restarting that volume. `55432` can be changed if occupied.

The Compose service initializes UTF-8 with `en_US.utf8` for Unicode case matching;
the [official PostgreSQL 17 image](https://github.com/docker-library/postgres/blob/master/17/bookworm/Dockerfile)
includes that locale. The server is separate from the schema/data setup: only
the explicit `seed` command creates application tables and loads fictional data.

### Terminal search

Initialize the dedicated sample separately with `python -m search_sample seed`
using the configuration above. Search only reads existing sample data; it never
seeds, resets, migrates or imports fixtures. Use the project environment's Python
(replace `python` below with `.\.venv\Scripts\python.exe` if it is not activated).

```powershell
python -X utf8 -m search_sample search --query "tình nguyện"
python -X utf8 -m search_sample search --query "sự kiện 5 điểm" --interpret
python -X utf8 -m search_sample search --course "CSC10004" --type assignment
python -X utf8 -m search_sample search --query "từ 5 điểm" --interpret --limit 10
python -X utf8 -m search_sample search --query "quantum pineapple"
python -X utf8 -m search_sample search
```

Only `search` accepts `--query`, `--interpret`, `--course`, `--type`, and `--limit`.
Query text maps to `keyword`; course maps to exact `filters.course` text; type maps
to a one-element `filters.types` list; limit maps to `limit`. Omitted values use
SearchService defaults: active tasks assigned to the sample owner, all six types,
20 results, deadline ascending with nulls last and ID tie-breaking. Blank query
text adds no keyword constraint. Types and limit bounds (currently 1–100) use the
existing request validator. Course text is not automatically a course identifier.

Without `--interpret`, text goes directly to `search_tasks()` for literal keyword
matching. With `--interpret`, `interpret_and_search()` applies the existing
[Vietnamese point grammar](docs/structured-search.md#vietnamese-training-point-interpretation),
intersects inferred and selected filters, and uses remaining text as keywords.
For example, `sự kiện 5 điểm` infers event and exactly five points, while `từ 5 điểm`
infers a minimum of five points with no type restriction. The CLI adds no parsing
rules of its own.

Output shows the original query, mode and readable filters, followed by one task
per block. Omitted/blank queries show `No keyword constraint.` Literal mode labels
selected filters including defaults; it does not interpret point expressions.
Interpretation mode uses existing metadata to show the remaining keyword and all
effective filters, including status, type, course and merged point constraints
(`exactly 5`, `at least 5`, `at most 5`, or `5 through 10`).

For example, `search --query "tình nguyện 5 điểm" --interpret` on an initialized,
unedited sample is expected to include:

```text
Original query: tình nguyện 5 điểm
Mode: interpreted
Remaining keyword: tình nguyện
Effective filters:
  Status: active
  Type: all six task types
  Training points: exactly 5

Returned page: 1 task(s)

Task ID: sample-description-only
Title: Bản tin sinh viên
Type: event
Training points: 5
```

Each block also shows relevant dates. Assignment/tuition deadlines use `Due`;
event/class/exam/personal intervals use separate `Starts` and `Ends` labels.
Other populated deadlines or interval endpoints are also displayed under their
own labels. Populated registration closing times use `Registration closes` and
never replace a deadline. Missing required display slots say `Not provided`;
unknown points say `Unknown`, distinct from `0` (the current SQL schema forbids
unknown points). Aware timestamps are converted to GMT+7, with seconds and any
nonzero microseconds preserved. Invalid/naive timestamps cause an error rather
than an assumed timezone. IDs and titles are printed in full on separate lines.

`Returned page` counts only the rows returned by this invocation, not total
database matches. A successful empty page retains query/filter context and prints
the exact message `No matching tasks`. It does not fall back to other tasks.

| Exit code | Meaning |
| --- | --- |
| 0 | Successful search, including an empty page |
| 2 | Invalid CLI arguments/request, unsupported or conflicting interpretation, missing configuration or driver prerequisite |
| 1 | Sample setup/owner failure, connection/query failure, unexpected command failure, or cleanup failure |

Normal output goes to stdout; errors go to stderr without tracebacks, SQL or raw
driver details. Error labels distinguish interpretation, sample setup, connection,
query and unexpected failures. Missing setup directs users to the explicit seed
command. The owner is resolved from PostgreSQL; the command uses a read-only
transaction, rolls it back when finished and closes the connection. Search output
is emitted only after cleanup succeeds. If rollback/close fails, the command
reports cleanup as unverified and exits nonzero; an existing primary error is
retained with its exit code and an additional cleanup notice.

Offline verification on 2026-11-08: `python -X utf8 -m unittest discover -s tests -q`
ran 140 tests: 120 passed, 20 PostgreSQL cases skipped. The 31 focused sample,
CLI and formatter tests use mocks/offline data, not a live database. Fixture
reproducibility/validation and `git diff --check` passed. Docker/PostgreSQL, the
driver and dedicated configuration were unavailable; real terminal output,
exit codes and sample preservation against PostgreSQL remain unverified.
The four representative search commands stopped
at the missing-configuration guard (exit 2, empty stdout); no connection was made.

### Data, ownership and expected results

`seed` creates only the reserved `search_sample` schema, its source-defined
tables, and an ownership/source marker. It reuses the 40 existing tasks via the
shared fixture adapter and adds five fixed text/visibility examples: 45 tasks,
two fictional users, 45 assignment links and two fixed calendar links. The owner
has 44 assigned tasks, of which 38 are active; one additional task belongs only
to the other user. All six types, statuses, zero/five/seven/ten points, missing
optional dates, deadline boundaries, overlaps and stable ties are represented.
Task dates are fixed around `2026-10-30`; the cross-field event uses UTC endpoints
equivalent to GMT+7 instants. Unknown points are not seeded because SQL forbids null.

Seeding twice must still report **45 task rows** on a fresh sample. Inserts use
conflict handling to avoid duplicates and preserve existing rows/edits. Seeding
does not silently restore edited values; use explicit reset to restore the demo.
The demonstration checks independently authored IDs and ordering, prints actual
IDs/titles, and fails on a mismatch rather than reporting an empty success.

| Example input | Expected IDs for the sample owner |
| --- | --- |
| `get_task_by_id("asg-csc10004-lab")` | `asg-csc10004-lab` |
| `get_task_by_id("sample-missing")` | `None` |
| Course `CSC10004`, assignment, deadline in `[2026-10-30, 2026-10-31)` with `+07:00` bounds | `asg-csc10004-lab` |
| `{"keyword":"tình nguyện","sort":"id"}` | `sample-cross-field`, `sample-description-only`, `sample-title-only` |
| Keyword `tình nguyện`, type `event`, points exactly 5 | `sample-description-only` |
| Keyword `50%_! O'Reilly` | `sample-literal` |
| `{"filters":{"statuses":["cancelled"]},"sort":"id"}` | `asg-cancelled`, `evt-cancelled` |
| `{"keyword":"quantum pineapple"}` | `[]` |

The demo also checks all 38 active tasks without a type restriction and a stable
course page. It reads existing rows through the real current SearchService; it
does not load JSON, seed data or reset anything during a search. User scope still
comes from `user_tasks`; no public/unassigned visibility policy is added.

### Tests, reset and shutdown

Offline tests and fixture checks:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -X utf8 fixtures/search/build_data.py --check
.\.venv\Scripts\python.exe -X utf8 fixtures/search/validate.py
git diff --check
```

The existing real PostgreSQL suite additionally requires the reviewed team's
`Database` package on `PYTHONPATH` plus its Pydantic v2 and python-dotenv dependencies.
It never uses the persistent demo schema. With that runtime available, explicitly
point its separate test settings at this dedicated local server:

```powershell
$env:RUN_SEARCH_POSTGRES_INTEGRATION = "1"
$env:SEARCH_TEST_DB_HOST = $env:SEARCH_SAMPLE_DB_HOST
$env:SEARCH_TEST_DB_NAME = $env:SEARCH_SAMPLE_DB_NAME
$env:SEARCH_TEST_DB_USER = $env:SEARCH_SAMPLE_DB_USER
$env:SEARCH_TEST_DB_PASSWORD = $env:SEARCH_SAMPLE_DB_PASSWORD
$env:SEARCH_TEST_DB_PORT = $env:SEARCH_SAMPLE_DB_PORT
$env:SEARCH_TEST_DB_CONFIRM = $env:SEARCH_TEST_DB_NAME
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p test_postgres_search_integration.py -v
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p test_postgres_search_integration.py -v
.\.venv\Scripts\python.exe -X utf8 -m search_sample demo
```

These mutation tests create and remove isolated `search_it_<uuid>` schemas and
must leave the persistent demonstration intact. See the
[integration safety contract](docs/structured-search.md#dedicated-postgresql-integration-tests).
Without explicit opt-in they skip; missing dependencies/settings after opt-in fail
setup rather than pretending real PostgreSQL was tested.

To remove and recreate only this setup's objects, explicitly run:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m search_sample reset --confirm-reset
.\.venv\Scripts\python.exe -X utf8 -m search_sample seed
.\.venv\Scripts\python.exe -X utf8 -m search_sample demo
docker compose -f compose.search-sample.yml down
```

Reset refuses an unmarked schema or a different owner/source marker. It drops only
the setup's tables and schema using `RESTRICT` in one transaction. Unrelated
objects or external dependencies make reset fail and roll back; nothing is
cascaded into unrelated tables. No database is dropped. `down` stops the owned
container/network and retains the volume; `up -d --wait` restarts it with its data.
Do not remove volumes as part of routine reset. No cleanup runs during `demo` or
ordinary SearchService queries.

### Schema source and integration limits

`search_sample/schema.sql` is the unchanged normalized SQL snapshot of
[`Database/Db_query.sql`](https://github.com/Loser-r-6663/Smart-Calender-for-FITHCMUS/blob/7aa63cfc5453a70a12b73b099c4f56e1dc583825/Database/Db_query.sql)
at Database commit `7aa63cfc5453a70a12b73b099c4f56e1dc583825`, checked alongside
[`task_schema.json`](https://github.com/Loser-r-6663/Smart-Calender-for-FITHCMUS/blob/7aa63cfc5453a70a12b73b099c4f56e1dc583825/Database/task_schema.json)
and the exact `Database/DatabaseManager.py`. A source hash is checked before schema
initialization. All four tables, foreign keys, defaults, checks, indexes and
`TIMESTAMPTZ` definitions are retained. Differences are the dedicated namespace
and the extra setup-ownership marker, not relaxed task constraints.

The shared adapter explicitly maps controlled fixture course codes to `course`,
removes obsolete `embedding`, translates recurrence and parses aware dates.
This does not establish exact course identity for arbitrary production course text.

The Database package is absent from this branch. The demo therefore uses the
explicit `SearchService.from_connection(connection, user_id=...)` seam and owns
the PostgreSQL connection itself. This is not a replacement DatabaseManager or
SQLite fallback. Normal manager-based usage is unchanged. SQL constraints validate
seeding, but the sample tool does not substitute for the team's Python model
validation; full DatabaseManager integration remains unverified until that runtime
and the dedicated suite are available. Schema/model discrepancies are retained in
the existing [Search documentation](docs/structured-search.md#discrepancies-requiring-database-confirmation).

Docker, PostgreSQL and the driver were unavailable during preparation. The setup
files, offline guards and deterministic expectations were checked; container
startup, real seeding/idempotency, demo retrieval and live cleanup remain unverified.
