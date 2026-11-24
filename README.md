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
  rows through `UserTaskRepository.pop_tasks()`, then persists scheduler tasks
  in per-user SQLite files under `LOCAL_TASK_DB_DIR` (default `Database/data`).
  Scheduling also persists its results and updates the user's training points.

Search and calendar refresh continue to call `get_tasks()` without consuming
rows. They currently cover authorized, source-enabled rows still in Supabase,
within the existing 1,000-row limit per repository. After the separate ingestion
workflow consumes a personal row, it is no longer available to these reads.
Whether Search should include consumed local tasks requires a separate coverage
and provenance decision: local scheduler tasks combine public and personal
inputs and do not retain `user_id`. No scope is inferred from a SQLite filename.

For offline verification, use the project environment and disable dotenv loading:

```powershell
$env:PYTHON_DOTENV_DISABLED = "1"
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -q
```

The mock NiceGUI browser checks use Playwright with installed Edge and fictional
source destinations. They do not require live Supabase accounts or running the
Crawler, scheduler, or `server.py`.
