# Smart Calendar for FIT-HCMUS

## Web client

The NiceGUI client is independently deployable from the Apify crawler. It can
run entirely offline with fixture data or read tasks through the existing
`Database` facade.

### Run with mock data

```powershell
python -m pip install -r requirements-mockweb.txt
$env:CLIENT_MODE = "mock"
python -m client.main
```

Open <http://127.0.0.1:8080> and sign in with:

- Username: `student`
- Password: `demo`

### Run with live data

Configure the existing Supabase variables, set `CLIENT_MODE=live`, and start
the same module. Calendar and Search read stored Supabase tasks using the public
client key and the authenticated session for personal rows. Opening Search
details does not fetch or consume tasks. The existing Run personal crawl action
runs the signed-in user's crawler separately from Search reads.

### Test

```powershell
python -m pytest -q
```

### Container

`Dockerfile.web` builds only the web client and the shared task/database
modules. It installs the full crawler dependencies declared by
requirements-web.txt for the existing personal refresh action.

## Crawler and local scheduler

Install `requirements.txt` for the Crawler and local scheduler entry points.
Copy `.env.example` to a private `.env` and configure the required values.
`SUPABASE_PUBLIC_KEY` is the client key; `SUPABASE_SECRET_KEY` is server-only.
`SUPABASE_ENCRYPTION_KEY` protects stored account data. Crawler sources may also
require `GEMINI_API_KEY`, Facebook credentials, or authenticated Portal/Moodle
sessions. The Apify configuration forwards the public and server key names to
the corresponding consumers.

- `python server.py` runs the public crawling pipeline by default. With
  `APP_ROLE=SERVER`, the Actor input selects public, personal, or all sources.
- `python user.py` starts the interactive `UserManager` authentication and local
  scheduling workflow. It reads public tasks and **consumes** personal Supabase
  rows through `UserTaskRepository.pop_tasks()` only after their local commit
  succeeds. Scheduling separately persists its results and updates the user's
  training points.

### Shared owner store for the single-machine demo

NiceGUI and `python user.py` use the same durable SQLite database per
**authenticated owner**. `LOCAL_TASK_DB_DIR` defaults to `Database/data` relative
to the repository root, independent of the process working directory. Set it to
the same absolute directory in both processes when deploying elsewhere. If the
web client runs in a container, mount this directory as a shared durable volume;
the scheduler process must see that same storage. Multi-device synchronization
is not provided.

Authenticated calendar open and explicit refresh read public and owner-scoped
personal Supabase tasks once per repository, at the existing 1,000-row read
limit. They commit original source facts locally, then construct Search and
calendar state from SQLite. Retained history has no 100-row local truncation.
Missing rows in a later remote response do not erase retained records. Source
preferences apply to the retained snapshot. Month navigation, queries, filters,
sorting and details reuse memory without SQLite or Supabase reads. The existing
Run personal crawl action may add newly crawled tasks to Supabase; it does not
consume/delete task rows or invoke scheduling. Its calendar callback performs
one refresh after the crawl. Guest reads remain public-only and never open an
owner's store.

Verified rows carry their authenticated owner, originating repository scope and
original UUID. Public and personal rows sharing a UUID remain independent by
`(scope, UUID)`. Original source facts and saved schedule state are stored
separately: source refresh cannot overwrite scheduled times or split sessions,
and scheduling cannot replace the facts shown in Search. Expired scheduled
history and consumed but unscheduled personal tasks remain searchable; expiry
and eligibility apply when scheduling, not when retaining Search history.

Existing ID-only databases migrate in a single SQLite transaction. Legacy rows
and their raw fields/schedules are preserved as `unknown` scope. They remain
available to the scheduler, but Search excludes them. A matching UUID, title,
source platform or owner filename does not promote a legacy row to a verified
scope. Fresh verified records coexist with unknown legacy records rather than
silently inheriting their provenance or schedules.

Scheduler ingestion commits all received source records before acknowledging
personal Supabase rows. A failed local write or commit acknowledges nothing.
Acknowledgements are restricted to that owner, original IDs and fetched
`updated_at` versions, so a concurrently updated row is not consumed. If an
acknowledgement fails after local commit, rerunning ingestion safely upserts the
same scoped records and preserves schedules. Public rows are never consumption
targets. Scoped scheduler reads/updates/deletes use `Task.key`; verified original
facts enter through `ingest_sources`, while schedule updates use `save_tasks`
or `save_schedule`. Previously saved schedules and recurring/split occurrences
are retained on subsequent scheduler runs.

For offline verification, use the project environment and disable dotenv loading:

```powershell
$env:PYTHON_DOTENV_DISABLED = "1"
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -q
```

The mock NiceGUI browser checks use Playwright with installed Edge and fictional
source destinations. They do not require live Supabase accounts or running the
Crawler, scheduler, or `server.py`.
