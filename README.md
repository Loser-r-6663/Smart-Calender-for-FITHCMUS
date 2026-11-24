# Smart Calendar for FIT-HCMUS

## Web client

The NiceGUI client is independently deployable from the Apify crawler. It can
run entirely offline with fixture data or read tasks through the existing
`Database` facade.

- [Client usage guide (Vietnamese)](CLIENT_GUIDE.md)
- [Server deployment guide (Vietnamese)](SERVER_GUIDE.md)
- [Public crawler guide (Vietnamese)](PUBLIC_CRAWLER_GUIDE.md)

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
the same module. The web process reads stored tasks through the database
facade. Personal Portal/Moodle crawls use the shared `DataProcessor` code;
public-source crawling remains in the separate Apify Actor deployment.
Connecting Moodle opens a local browser for Google sign-in, so the web process
must run on the same computer as the browser; this flow is unavailable in the
headless `APP_ROLE=SERVER` container.

### Test

```powershell
python -m pytest -q
```

### Container

`Dockerfile.web` includes the web client, shared task/database modules, and
`DataProcessor` for personal crawls. It installs Playwright and Chromium;
public-source crawling remains in the separate Apify Actor deployment. Moodle
Google sign-in requires a local, non-server process rather than this container.
