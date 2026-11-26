# Background preparation and first-search feedback

This follow-up builds on the **uncommitted** P implementation at HEAD
`961174a20f6feed7b6f780b4626cf4dc144b5bc3`. The earlier P reports in
[PERFORMANCE.md](PERFORMANCE.md) remain historical measurements. They do not
include the background work described here.

The optional model, immutable revision, CPU runtime and cutoff **0.86** are
unchanged; see [HYBRID.md](HYBRID.md) for installation. Model weights stay
outside Git. No query/task text leaves the machine.

## Lifecycle and limits

After a successful authorized, source-enabled snapshot load, the controller
schedules explicit `HybridSearch.begin_preparation()` / `prepare_batch()` work.
The calendar page releases it after connection and two animation frames so
login/navigation and the calendar's first paint do not await model setup.
Keyword-only installations neither initialize nor prepare a model.

Preparation processes at most 16 passages at a time (one initial passage to
discover vector size). The controller releases its Search lock after **each**
batch and gives queued foreground requests priority. The ranker's encoder lock
also protects direct callers. In-progress model construction or a batch cannot
be interrupted. A foreground request reuses prepared vectors and fills only
its eligible misses; it does not race a background encoder.

The existing per-controller LRU limits remain **2,048 entries / 8 MiB vector
payload**. The 384-double model vectors use 3,072 bytes each; 1,008 use
3,096,576 bytes, and the entry limit caps payload at 6 MiB for this model.
These bounds exclude model weights, snapshots, metadata and temporary inference
arrays. Preparation never evicts: it stops **partial** when capacity is reached,
rather than cycling through an oversized snapshot. Foreground search retains
the existing LRU eviction policy. It can still encode uncached/evicted passages.
`preparation_status` distinguishes pending/running, complete, partial,
unavailable, disabled and cancelled; partial does not mean the whole snapshot
is ready.

Snapshot/token identity, full scoped UUID, title/description fingerprint and
model configuration govern reuse. Refresh/source changes/session invalidation
advance cache epochs. Obsolete work cannot cache vectors or publish readiness
for a replacement snapshot. Only the controller's authorized source-filtered
records are prepared. No tasks are fetched, written, scheduled or deleted.

## Search feedback

A submitted semantic query immediately renders its current keyword hits as
**Keyword matches — semantic search in progress**. With no literal hits it
shows **Searching by meaning…**, rather than an empty-result claim. Completion
replaces these with **Hybrid results**, or explicit keyword fallback feedback
when local inference is unavailable. Exact-title/course, blank and point-only
queries keep their existing keyword shortcut. No extra Search controls were
added. The inferred point-constraint summary is removed; interpretation,
effective filters, validation, positive row points and zero/missing detail
values remain intact.

Request/query/filter/snapshot/session guards discard stale completions. A
preliminary row resolves against the current authorized snapshot, and the
dialog restores focus by scoped key if final rendering replaced its opener.
Draft/submitted queries, Calendar state and source/account protections remain
independent.

## Reproduce the measurements

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:SEARCH_SEMANTIC_MODEL = "$env:LOCALAPPDATA\SmartCalendar\models\multilingual-e5-small"
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.preparation_benchmark --reference-archive fixtures/search_semantic/preparation_reference.json --output fixtures/search_semantic/preparation_before.json
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.preparation_benchmark --output fixtures/search_semantic/preparation_after.json
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.compare_preparation
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.check_prepared
```

Run sequentially without other tests/inference. The source archive contains the
four P modules captured before this follow-up, with verified SHA-256 hashes.
It replays the actual prior popover/controller/ranker/dialog without switching
branches. Both runs use equivalent instrumentation, normal application
connection settings, installed Edge at 1440x1000 and the real local CPU model.
The 14- and 1,008-record fictional workloads are exactly `benchmark.tasks(size)`
from P: the frozen 14 task facts projected into one authorized mock session,
and 72 indexed repetitions with stable UUID5 keys. This measures loaded
snapshots, not live pagination, authentication or permissions.

Each scenario uses a fresh application/browser/model process. The scenarios
are immediate literal (`thời điểm`), immediate zero-overlap paraphrase
(`hạn cuối đóng học phí`), and the same paraphrase after actual preparation
completion. The prior P version has no preparation and therefore searches its
fresh snapshot. Calendar readiness is mock-session navigation to visible
toolbar/handshake. Submit timing starts at Enter and waits for a unique
current-operation phase marker plus two animation frames. Background completion
is awaited through the controller task, not a truthy asynchronous polling
expression. Counts separate foreground queries/passages and background passages;
encode time includes tokenization/ONNX/pooling. Model construction is separate.
Opening and closing an original source-linked detail is checked without reads.
Preparation duration runs from snapshot binding to terminal status; it includes
the first-paint gate and time yielding to foreground searches. It is not pure
background inference time, which is recorded separately.

One observation per scenario is descriptive evidence, not a latency guarantee
or a statistical median. Process-cold startup does not flush OS disk caches.
Pilot/intermediate reports are preserved separately and excluded from final
comparison. In particular, the first pilot exposed preparation running before
calendar paint; the UI release gate corrects that ordering. Optional dependency
imports can still briefly occupy Python's interpreter even on a worker thread;
foreground searches may wait for the current initialization/batch. An immediate
unprepared broad search still has a substantial final-retrieval cost.

The prepared regression command compares **all complete ordered hit lists**
for the frozen 31 cases against the captured P ranker using the real model. Its
new report is `semantic_prepared_regression.json`. This is regression
verification, not a new blind retrieval-quality evaluation. Frozen inputs,
judgments, matcher/report fingerprints and historical semantic reports remain
unchanged.

## Observed UI measurements

Final paired observations are in `preparation_before.json`,
`preparation_after.json` and `preparation_comparison.json`. Times below are
milliseconds, one fresh process per row/implementation. The baseline is the
captured uncommitted P version, not a claim that P was committed.

| Records / scenario | Calendar before / after | Before final | After preliminary | After final | Preparation to terminal status |
| --- | ---: | ---: | ---: | ---: | ---: |
| 14 / immediate literal | 5,914 / 5,168 | 7,830 | 393 | 7,423 | 12,215 |
| 14 / immediate paraphrase | 4,909 / 4,998 | 6,597 | 382 | 11,939 | 17,119 |
| 14 / prepared paraphrase | 5,276 / 5,262 | 8,452 | not observed | 329 | 11,012 |
| 1,008 / immediate literal | 6,214 / 6,453 | 61,528 | 1,015 | 59,836 | 70,993 |
| 1,008 / immediate paraphrase | 5,643 / 5,543 | 55,678 | 1,027 | 51,025 | 60,729 |
| 1,008 / prepared paraphrase | 5,971 / 6,004 | 61,243 | 509 | 986 | 57,295 |

The immediate queries were submitted while preparation was pending/running.
Literal hits became usable at the preliminary time; a zero-overlap paraphrase
instead displayed the semantic-searching state at that time. It did **not**
have a relevant row until final completion. Prepared queries encoded **one
query and zero passages**, with **zero additional task reads**. Opening their
original details and checking the source destination also made zero reads.
All six complete ordered result sets match the before run.

In the prepared scenarios, model construction took **5,951 / 6,060 ms** for
14 / 1,008 records, background passage encoding **637 / 47,135 ms**, and query
encoding **34 / 78 ms**. The remaining **295 / 909 ms** of submit-to-final time
includes UI delivery, scoring and rendering. No additional task fetching or
schedule work was shifted into refresh. Preparation now consumes CPU after
first paint and repeats for replacement snapshots; it is an intentional cost.

The prepared first submission improves by **8,123 ms (96.1%)** and
**60,257 ms (98.4%)** in these observations. Cold completion is **not**
uniformly faster: the small immediate paraphrase regressed from 6.60 to
11.94 seconds, with measured model startup increasing from 5.35 to 12.13
seconds. The large immediate final result still took 51–60 seconds. These
single observations cannot separate machine variance from scheduling overhead;
preliminary feedback and ready-cache results are the demonstrated benefits.
Calendar readiness remains roughly 5–6.5 seconds in this mock application,
without waiting for the 11–57-second no-foreground preparation runs. This is
not an authenticated live login measurement or a promise of instantaneous
unprepared semantic results.

## Verification

The real-model prepared regression exits **0**: **3/3 tuning**, **1/4 held-out**,
**0/4 unrelated false hits**, zero visibility/point/boundary/control violations.
All 31 complete ordered sets equal the captured reference, and top-three
outcomes equal the historical performance report. H-X02 and H-V05 retain
their single expected exact-title record. The frozen keyword `--check`
reproduces **1/3 tuning**, **0/4 held-out**, **0/4 unrelated false hits** and
zero violations byte-for-byte.

With `PYTHON_DOTENV_DISABLED=1`, model configuration removed, fresh writable
`--basetemp` directories and `-p no:cacheprovider`, the focused command passed
**64 tests in 348.63 seconds**, zero failures/errors/skips:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -q tests/test_search_preparation.py tests/test_search_embedding_cache.py tests/test_search_semantic.py tests/test_semantic_ui.py tests/test_search_preliminary_ui.py tests/test_search_ui.py tests/test_compact_search_ui.py --tb=short -p no:cacheprovider --basetemp=<fresh-directory>
```

Deterministic encoders test cooperative priority, independent entry/byte bounds,
no eviction churn, fallback, refresh/changed text/source/account collisions,
logout/expiry and stale work. Actual Edge controls test preliminary keyword
details under both scoped UUIDs, final replacement/focus, zero-keyword searching,
Clear while pending, final empty state, removed summaries, point membership,
row/detail facts, independent Calendar controls, keyboard, desktop/narrow
popover/dialog scroll and source destinations. These mocked lifecycle checks
are distinct from the real model's retrieval and latency evidence above.

The final complete keyword-only offline run passed **226 tests and 512
subtests in 614.93 seconds**, **zero failures, errors or skips**, with 48
existing BaseTask/Pydantic deprecation warnings:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
Remove-Item Env:SEARCH_SEMANTIC_MODEL -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -q --tb=short -p no:cacheprovider --basetemp=<fresh-directory> --junitxml=$env:TEMP\preparation-full.xml
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.run_keyword --check
```

Focused/full outputs are `$env:TEMP\preparation-focused.txt` and
`$env:TEMP\preparation-full.txt`. No dependencies were installed and no live
accounts, operational crawler/scheduler/server.py or external inference service
were used. Mock applications and browsers were closed. The existing model
assets remain outside Git; all implementation changes remain unstaged.
