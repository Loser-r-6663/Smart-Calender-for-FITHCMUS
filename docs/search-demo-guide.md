# Search Demonstration Guide

The Search MVP retrieves tasks assigned to a trusted user across class, assignment,
exam, event, personal and tuition. It supports exact lookup, structured filters,
literal title/description keywords, deterministic ordering/pagination, and a small
Vietnamese training-point grammar. Omitted types mean all six types; structured
search defaults to active status. Exact lookup retains all-status behavior.
The [Search contract](structured-search.md) defines the full interface and limitations.

## Revisions and prerequisites

- Reviewed Search baseline: `df3cc61d5b490b7d3a292bd87195e8f288ebdbda` on `Search`.
  The interpreted-demo and verification additions are working-tree changes over
  this baseline; include that diff when reproducing the demonstration. Record
  `git rev-parse HEAD` and `git diff --stat` with any later verification.
- Required Database revision: `7aa63cfc5453a70a12b73b099c4f56e1dc583825`.
  The selected interface is `Database/DatabaseManager.py`, not the lowercase module.
  `tests/postgres_search_support.py` pins SQL, manager and task-repository hashes;
  source drift must be reviewed rather than bypassing those guards.
- Python 3.10+, Docker with Compose v2 and the configured PostgreSQL 17 Bookworm
  image; `psycopg2-binary` in the project environment. Manager integration additionally
  needs the complete reviewed Database package on `PYTHONPATH`, Pydantic v2 and
  python-dotenv. Preserve unrelated `PYTHONPATH` entries.

Follow the [sample setup](../README.md#local-postgresql-search-sample) for the venv,
private password prompt and explicit configuration. All six variables are required:

| Variable | Dedicated local example |
| --- | --- |
| `SEARCH_SAMPLE_DB_HOST` | `127.0.0.1` |
| `SEARCH_SAMPLE_DB_NAME` | `calendar_sample_search_test` |
| `SEARCH_SAMPLE_DB_USER` | `search_sample` |
| `SEARCH_SAMPLE_DB_PASSWORD` | `<private-local-secret>`; enter privately, never capture it |
| `SEARCH_SAMPLE_DB_PORT` | `55432` |
| `SEARCH_SAMPLE_DB_CONFIRM` | Exactly the configured database name |

Never use shared/production credentials. The target must be loopback and the
database name must end in `_search_test`. Existing target, ownership and source
guards remain mandatory. Use the project environment's `python` below, or replace
it with `.\.venv\Scripts\python.exe` as in the README.

## Initialization and teacher demonstration

Initialization is separate from retrieval. On a fresh dedicated sample, both seed
runs must report 45 tasks; existing rows/edits are preserved rather than overwritten.
No sample records or counts changed for this demonstration.

```powershell
docker compose -f compose.search-sample.yml up -d --wait
python -X utf8 -m search_sample seed
python -X utf8 -m search_sample demo
python -X utf8 -m search_sample search --query "tình nguyện"
python -X utf8 -m search_sample search --query "sự kiện 5 điểm" --interpret
python -X utf8 -m search_sample search --course "CSC10004" --type assignment
python -X utf8 -m search_sample search --query "từ 5 điểm" --interpret --limit 100
python -X utf8 -m search_sample search --query "quantum pineapple"
```

The scripted demo checks exact/missing lookup, all types, fixed demonstration
deadline dates `[2026-10-30, 2026-10-31)` in GMT+7, literal keywords/punctuation,
combined filters, status, stable pagination, no matches and the four interpreted
queries below. Each case compares authored IDs; interpreted cases also compare
original query, remaining keyword, inferred filters and effective filters.
It deliberately requests exactly five points with selected maximum three and
requires a constraint-conflict `SearchInterpretationError`. Missing/wrong errors,
unexpected failures or mismatches fail the command. Final success is printed only
after every check and read-transaction cleanup succeeds. The demo is read-only.

| Query | Effective constraints (active status unless selected otherwise) | Expected sample IDs |
| --- | --- | --- |
| `5 điểm` | Exactly 5; no type restriction; no remaining keyword | Five-point group below |
| `từ 5 điểm` | At least 5; no type restriction; no remaining keyword | Five-point group plus `evt-beach`, `evt-green`, `sample-cross-field` (17 rows) |
| `sự kiện 5 điểm` | Event, exactly 5; no remaining keyword | Five-point group |
| `tình nguyện 5 điểm` | Exactly 5; remaining keyword `tình nguyện`; no type restriction | `sample-description-only` |

The independently authored five-point group, in ID order, is:

```text
evt-cancel, evt-end-midnight, evt-future-reg, evt-missing-both,
evt-missing-end, evt-missing-start, evt-next-midnight, evt-overlap,
evt-reg-after, evt-reg-before, evt-reg-exact, evt-speaking, evt-today,
sample-description-only
```

These 14 persistent sample records happen to be events; bare point expressions
do not infer event. Isolated integration records verify equal-point results across
all six types. Scripted interpreted cases use ID ordering and limit 100; terminal
commands retain default deadline ordering. Counts describe the returned page.

Literal `tình nguyện` finds `sample-cross-field`, `sample-description-only` and
`sample-title-only`. The course/assignment command finds `asg-overdue`,
`asg-csc10004-lab` and `asg-csc10004-project` in default deadline order.
`quantum pineapple` returns an empty page with `No matching tasks` and exit 0.
For a separate error example, append `--type exam` to the interpreted event command:
it must report a conflict on stderr and exit 2. Setup/query/cleanup failures use
exit 1; missing configuration/driver or invalid arguments use exit 2.
The [terminal output policy](../README.md#terminal-search) explains GMT+7 date
labels/precision and readable filters. No successful live output was captured here;
the README output example is illustrative expected output, not a database transcript.

## Verification and repeatability

With the reviewed Database runtime available, copy the dedicated sample settings
explicitly to all six `SEARCH_TEST_DB_*` variables and set
`RUN_SEARCH_POSTGRES_INTEGRATION=1`, following the
[exact configuration commands](../README.md#tests-reset-and-shutdown).
Each invocation below starts a fresh Python process. Integration tests create
uniquely named `search_it_<uuid>` schemas, register cleanup before seeding, remove
their own committed mutations and verify each schema is absent. They do not use
or reset the persistent `search_sample` schema.

```powershell
python -X utf8 -m unittest discover -s tests -q
python -X utf8 fixtures/search/build_data.py --check
python -X utf8 fixtures/search/validate.py
python -X utf8 -m unittest discover -s tests -p test_postgres_search_integration.py -q
python -X utf8 -m unittest discover -s tests -p test_postgres_search_integration.py -q
python -X utf8 -m search_sample demo
git diff --check
```

Require both integration runs to pass without skips, and run the demo afterward
to confirm all persistent sample IDs/metadata still match. Keep the dedicated
settings unchanged between runs. Explicit reset is only for a reviewed sample
restoration; use the [existing reset/shutdown commands](../README.md#tests-reset-and-shutdown).
Never remove unrelated schemas or volumes as routine cleanup.

Actual verification on 2026-11-08 used Windows NT `10.0.26300.0`, PowerShell `7.6.9`
and Python `3.14.7`:

| Check | Actual result |
| --- | --- |
| Full offline suite | 147 discovered: 127 passed, 0 failed, 0 errors, 20 PostgreSQL skips |
| Scripted-demo orchestration tests | 6 passed using mocked service results; no live SQL |
| Interpretation/boundary tests | 9 passed; the access sentinel proves invalid requests never obtain a connection |
| Integration process 1 | 0 passed, 0 failed, 0 errors, 20 skipped (opt-in unset) |
| Integration process 2 | 0 passed, 0 failed, 0 errors, 20 skipped (opt-in unset) |
| Fixture checks | Reproducible fixtures; validated 40 tasks, 32 queries, 3 scenarios |
| Scripted demo and four representative terminal searches | Each exited 2 at missing sample configuration, with empty stdout; no connection |
| Authored point-ID audit and documentation checks | Offline sample-field audit, links/paths and `git diff --check` passed |

Docker/PostgreSQL, psycopg2, the reviewed Database package and dedicated settings
were unavailable. No software was installed or system configuration altered.
No PostgreSQL version/dependency versions or successful database output could be
recorded. Live retrieval, two-run cleanup, successful demonstration execution and
persistent sample preservation remain unverified; skips are not live passes.

Direct sample execution uses `SearchService.from_connection()`; the CLI owns and
closes its read-only connection. It does not verify the selected DatabaseManager.
The guarded integration suite uses the actual manager and TaskRepository, including
committed writes in isolated schemas. Offline mocks/SQLite tests verify neither
path against PostgreSQL. Record actual server/dependency versions, pass/fail/skip
counts and non-sensitive output when that environment is supplied.

## Design and computational-thinking contribution

The flow is **input → interpretation → validation → SQL search → output**.
Literal mode omits interpretation. Interpreted mode first validates the request,
recognizes a limited grammar, intersects typed/selected constraints and validates
the merged request before delegating to the same SearchService and parameterized
PostgreSQL compiler. Presentation uses existing metadata; it does not parse again.

- **Decomposition:** independent interpretation, request validation, retrieval and
  terminal presentation keep database access and display separate.
- **Abstraction:** supported language becomes numeric/type filters plus remaining
  literal keywords. Metadata makes that transformation inspectable.
- **Pattern recognition:** Unicode-normalized, case-insensitive complete expressions
  use a deterministic grammar. `N điểm`, `N điểm rèn luyện`, `N đrl` mean exact
  points; prefix `từ` means minimum. `sự kiện` infers event only with recognized points.
- **Algorithm design:** compatible constraints intersect; incompatible bounds/types
  fail. SQL combines hard filters, literal keyword terms, user scope, stable ordering
  and pagination. Remaining words require case-insensitive literal substrings in
  title/description; points are not ranking hints.
- **Verification:** authored IDs/metadata, boundary sentinels, failure-injection
  orchestration checks and guarded repeatable integration tests exercise distinct
  responsibilities without treating mocks as database evidence.

The implemented Search contribution includes structured PostgreSQL retrieval,
deterministic interpretation, literal keyword matching, terminal formatting,
isolated sample utilities and tests. The demonstration includes interpreted-query
assertions and the existing self-checking demo; it does not redefine team schema.
Supported point values reuse validation (0–100). Negation, decimal/range syntax,
unsupported comparisons and multiple expressions are rejected conservatively;
unaccented variants, extra type synonyms, embeddings and general Vietnamese
language understanding are outside scope. The
[grammar limitations](structured-search.md#vietnamese-training-point-interpretation)
and [remaining integration decisions](structured-search.md#remaining-integration-decisions)
still apply, especially free-text course identity, unknown points and the absent
Database runtime. No visibility policy or database contract changes are implied.
