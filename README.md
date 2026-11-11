# Smart Calendar for FIT HCMUS

## Branch Contents

- **Backend/Crawler** contains the six crawlers and `RawTasks.txt`. The public crawlers are FIT, HCMUS, and OSA. The authenticated or session-based crawlers are Portal, Moodle, and Facebook.
- **Backend/Parser** adapts raw crawler records, removes duplicates, extracts structured task data with the configured LLM provider, validates it, and sends it to the Database API.
- **Backend/Scheduling** runs `BranchAndBoundScheduler` via `SchedulingService` over active database tasks and per-user DRL scores (`user_drl_scores`), expanding weekly Portal `recurrence` slots and optionally persisting selected events to `user_tasks` and `daily_tasks`.
- **Database** contains the FastAPI database API, PostgreSQL connection and repository code, authorization settings, and `Db_query.sql`.
- `main.py` runs the live pipeline. `tests` contains offline unit tests and `tests/pipeline_demo.py`.

- **Flow**:
```text
Crawler -> Parser -> Database API -> PostgreSQL
```

The crawler stage fetches records from all six sources. The parser normalizes and deduplicates them, calls the configured LLM provider when extraction is needed, validates the resulting tasks, and sends them over the authenticated Database API. The API validates requests and persists tasks and related records in PostgreSQL.

`main.py` currently runs all six crawlers sequentially in this order: Portal, Moodle, FIT, HCMUS, OSA, Facebook. If one crawler fails, its result becomes an empty list and the other crawlers continue. There is no source-selection option in `main.py` yet.

## Requirements

- Windows with Python 3.12 or newer
- PostgreSQL
- Playwright Chromium browser

## Setup

Run these commands from the project directory in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

## Configuration

Copy the example environment file and edit the copy without committing it:

```powershell
Copy-Item .env.example .env
```

- Set the PostgreSQL group: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.
- Set the parser provider group: `LLM_PROVIDER` and the matching provider credentials, such as `GEMINI_API_KEY` and `GEMINI_MODEL` or the `OPENAI_*` values.
- Set the Database API group: `DATABASE_API_URL`, `DATABASE_API_TIMEOUT_SECONDS`, `ADMIN_API_KEY`, `LLM_API_KEY`, and `DATABASE_API_KEY`. `ADMIN_API_KEY` and `LLM_API_KEY` must be different secrets. With the current integration choice, `DATABASE_API_KEY` must equal `ADMIN_API_KEY`.
- Set `PORTAL_USERNAME` and `PORTAL_PASSWORD` for Portal, and `FB_USERNAME` and `FB_PASSWORD` for Facebook. Moodle uses a browser session and may require interactive Google login.

Do not put real credentials or API keys in this README or in source control.

## Database Setup

Create the database named by DB_NAME in .env, then apply the schema in your Postgre database with `Db_query.sql` (could use PgAmin 4 for this)

Use the actual `DB_NAME`, `DB_USER`, and `DB_PASSWORD` values from `.env`. 

You can check what tasks are currently in the database by going to Tables -> tasks

## Run the Database API

Start PostgreSQL first, then, from the project root directory containing `Database`, `Backend`, and `main.py`, run:

```powershell
.venv\Scripts\Activate.ps1
.venv\Scripts\python.exe -m uvicorn Database.api:app --reload
```

Do not run this from inside the `Database` directory because the absolute `Database.*` imports require the project root on Python's import path.

The API listens at http://127.0.0.1:8000 by default. Keep this process running before starting the live pipeline.

## Running main.py

With the API running in another PowerShell window:

```powershell
.venv\Scripts\Activate.ps1
python main.py
```

This runs every crawler, parses the combined results, and persists valid tasks. Parser deduplication state is stored in `.parser-dedup.json`, whose path can be changed with `PARSER_DEDUP_STATE_PATH`. Treat it as local state and do not commit it.

## Pipeline demo

`tests/pipeline_demo.py` runs the real parser and Database API pipeline using the configured LLM/API settings. It reads the crawler output from `Backend/Crawler/RawTasks.txt` instead of having the crawler active:

```powershell
python tests\pipeline_demo.py
```

The demo is not fully offline and still needs the configured provider, API, database, and authorization settings as applicable.

## Running the Scheduler

With PostgreSQL updated using `Database/Db_query.sql` (including `user_drl_scores`) and the Database API running:

- Inspect tasks via `GET /tasks` and manage a user's current 5-category DRL points via `GET/PUT/PATCH /users/{user_id}/drl`.
- Trigger scheduling for a user via `POST /users/{user_id}/schedule` (using `ADMIN_API_KEY`; pass `persist: true` to assign selected events and write `daily_tasks`).
- Run scheduler unit tests:

```powershell
python -m unittest tests/test_scheduling_service.py Backend/Unit_Test/test_branch_and_bound_scheduler.py -v
```
