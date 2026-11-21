# Smart Calendar for FIT-HCMUS

## Web client

The NiceGUI client is independently deployable from the Apify crawler. It can
run entirely offline with fixture data or read tasks through the existing
`Database` facade.

### Run with mock data

```powershell
python -m pip install -r requirements-dev.txt
$env:CLIENT_MODE = "mock"
python -m client.main
```

Open <http://127.0.0.1:8080> and sign in with:

- Username: `student`
- Password: `demo`

### Run with live data

Configure the existing Supabase variables, set `CLIENT_MODE=live`, and start
the same module. The web process reads stored tasks only; crawler execution
remains in the separate Apify Actor deployment.

### Test

```powershell
python -m pytest -q
```

### Container

`Dockerfile.web` builds only the web client and the shared task/database
modules. It deliberately excludes Playwright, Gemini, and the Apify crawler
runtime.
