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

## Crawler and scheduler

Install `requirements.txt` for the Crawler and scheduler entry points.
Copy `.env.example` to a private `.env` and configure the required values.
`SUPABASE_PUBLIC_KEY` is the client key; `SUPABASE_SECRET_KEY` is server-only.
`SUPABASE_ENCRYPTION_KEY` protects stored account data. Crawler sources may also
require `GEMINI_API_KEY`, Facebook credentials, or authenticated Portal/Moodle
sessions. The Apify configuration forwards the public and server key names to
the corresponding consumers.

- `python server.py` runs the public crawling pipeline by default. With
  `APP_ROLE=SERVER`, the Actor input selects public, personal, or all sources.
- `python user.py` starts interactive authentication and the separately invoked
  scheduler. It reads original Supabase tasks without consuming them and stores
  per-user scheduling fields in `user_task_state`.

### Calendar, task management and Search snapshots

The merged live client uses FE's paginated `get_tasks(None)` reads for public and
owner/token-bound personal repositories. Calendar and scheduling apply the
owner's `user_task_state` overlay. Editing, removing/restoring, pinning and
creating tasks retain the incoming FE repository and state-persistence paths.
The supplied SQL is in `Database/Repository/user_task.sql` and
`custom_task_migration.sql`; no live schema changes were applied during merge
verification. Public client configuration and server-only secrets remain separate.

Calendar and Search share one completed authorized refresh. Original task reads
paginate in stable `id.asc` order, 1,000 rows per page through exhaustion, with
no total Search cap. Guests read public tasks only; personal pages use the
current session token and authenticated owner ID with the public client key.
A failed later page is a read error and never publishes a partial snapshot.
Snapshot `row_limit=None` means no requested total limit, including successful
empty scopes. Source preferences apply to both views.

Search records preserve original facts before scheduling overlays and calendar
occurrence expansion. Search supports class, assignment, event, announcement
and personal types. The Personal filter selects the stored type; private
assignments still appear under Assignments. Search selection uses `(scope, UUID)`
and opens the original details without another task request. Query, filter,
sort and month navigation reuse the loaded snapshot.

The implementation assumes UUIDs are globally unique across public and personal
originals, as an application decision supplied by the user, without separate
confirmation from the database owner. Repeated IDs and cross-source collisions
fail before an ambiguous `user_task_state` overlay is applied. In-memory mock
fixtures still support scoped UUID collisions independently. No schema change
or stored scope field is introduced.

Original facts remain separate from scheduling flags. The original task tables
are not consumed by the incoming FE scheduler. The personal-crawl wrapper adds
owner-scoped tasks without deleting expired rows or invoking scheduling itself;
the FE calendar refresh also refreshes an already-open weekly schedule.

The frozen keyword baseline can be reproduced with
`python -m fixtures.search_semantic.run_keyword --check`. Its corpus, judgments,
splits and per-query results are unchanged; the reviewed matcher fingerprint
update for the additional personal type is recorded in the fixture README.

### Existing SQLite utilities

The old owner-store utilities and migration tests remain in the repository for
review of the earlier retention contract. The active merged client and
`UserManager` no longer read or write those stores. Existing files are not
migrated or deleted automatically. Independent legacy utility tests remain.
Active application coverage now exercises Supabase originals, scheduling
overlays, page failures, owner isolation, source preferences and snapshot reuse;
the retired application SQLite ingestion/rollback/consumption assertions have
been replaced or removed. No SQLite store is opened by the active Search path.

For offline verification, use the project environment and disable dotenv loading:

```powershell
$env:PYTHON_DOTENV_DISABLED = "1"
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -q
```

The mock NiceGUI browser checks use Playwright with installed Edge and fictional
source destinations. They do not require live Supabase accounts or running the
Crawler, scheduler, or `server.py`.
