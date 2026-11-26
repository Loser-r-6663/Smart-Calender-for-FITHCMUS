# Loaded-task latency benchmark

Baseline: committed `961174a20f6feed7b6f780b4626cf4dc144b5bc3` (6A).
The model, revision, cutoff 0.86 and CPU runtime are unchanged. See HYBRID.md
for optional installation; inference and task/query contents remain local.

The background-preparation follow-up is measured separately in
[PREPARATION.md](PREPARATION.md). The numbers below preserve the original
uncommitted P observations. Re-running `working` uses the current code,
including preparation; use the newer runner to separate that background work.
The committed baseline replay adapts the optional first-paint hook as a no-op.

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:SEARCH_SEMANTIC_MODEL = "$env:LOCALAPPDATA\SmartCalendar\models\multilingual-e5-small"
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.benchmark --implementation baseline --trials 2 --output fixtures/search_semantic/latency_before.json
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.benchmark --implementation working --trials 2 --output fixtures/search_semantic/latency_after.json
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.compare_latency
```

These commands replace performance measurements, not the frozen keyword or
historical semantic reports. Run sequentially, without concurrent tests/model
inference. The baseline was measured before runtime edits on the clean 6A
checkout. The runner can also replay the committed semantic/controller/popover
sources through `git show`, without switching branches or changing Git state.
After the initial baseline, this replay loader was hardened to pin all three
modules. Timer/counter hooks were unchanged; hence the original before/after
harness file hashes differ. `latency_baseline_replay.json` verifies the pinned
replay has identical small-corpus ordered keys and passage counts.

## Workload and measurement

- Two fresh application/browser processes per corpus and implementation. These
  are descriptive medians and slowest-of-two trials, not confidence intervals.
  Model startup is cold **process** initialization, not a flushed OS disk cache.
- Installed Edge, desktop 1440x1000, CPU ONNX with two intra-op threads, pinned
  multilingual E5-small revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`.
- Small: all 14 frozen task texts/facts, projected into one fictional authorized
  demo session with deterministic UUID5 identities. Personal ownership is
  reassigned to that fictional viewer so all texts can be timed together.
- Large: `benchmark.tasks(1008)` generates 72 repetitions of the 14 facts, with
  stable unique UUID5 keys and indexed title suffixes. This is enough records
  for two 1,000-row pages. It benchmarks the **completed in-memory snapshot**
  through a controlled mock load, not live Supabase pagination or permissions.
- Queries: `hạn cuối đóng học phí`, then a different semantic query
  `tìm chỗ làm lập trình`, repeat, Title A–Z, Notices, then All types.
  Both queries actually invoke the model. Before refresh, Clear returns the
  form to idle so refresh cannot hide precomputation in a submitted search.
- Actual Enter/control activation to new rendered results, followed by two
  browser animation frames. Input filling precedes timing. A unique operation
  token is added after results finish rendering, excluding earlier rows and
  pending/loading feedback. Sort/filter timings include dropdown interactions.
- Inference time wraps `LocalEncoder.encode`: tokenization, ONNX, pooling and
  normalization. Startup wraps encoder construction separately. Encoder calls
  mean encode invocations, not internal ONNX batches of up to 16 inputs. Query
  and passage **counts** are recorded separately, as are mock task reads.
- The same 300-second reconnect tolerance is used for both measured runs. The
  original synchronous large search exceeded normal heartbeat tolerances and
  reloaded the page; `latency_pilot.json` records that failed default-timeout
  pilot. The product timeout is unchanged. The optimized UI runs inference off
  the event loop, so it does not rely on the extended benchmark tolerance.
- `latency_after_pilot.json` is excluded from acceptance: focused tests ran
  concurrently with it. `latency_after.json` is the sequential quiet rerun.

## Measured visible results

Times are milliseconds. Raw rows include inference/startup, encoder calls,
queries/passages, task reads and complete ordered scoped keys. All 40 operation
outcomes have unchanged ordered keys. Every different/repeat/sort/filter warm
operation encodes **one query, zero passages, zero task reads** after caching.

| Records | Operation | Before median | After median | Before slowest | After slowest |
| --- | --- | ---: | ---: | ---: | ---: |
| 14 | app_open | 1999.7 | 2188.0 | 2268.5 | 2379.0 |
| 14 | cold_search | 3503.6 | 3526.6 | 3557.8 | 3540.3 |
| 14 | snapshot_refresh | 271.2 | 314.0 | 272.4 | 327.9 |
| 14 | first_fresh_search | 624.1 | 866.9 | 881.3 | 886.7 |
| 14 | different_query | 338.1 | 63.3 | 343.0 | 65.4 |
| 14 | repeat_query | 598.8 | 71.8 | 857.8 | 72.2 |
| 14 | sort_title | 571.4 | 308.7 | 589.1 | 309.4 |
| 14 | narrow_type | 378.3 | 262.4 | 390.8 | 270.8 |
| 14 | widen_type | 450.6 | 238.6 | 459.0 | 271.9 |
| 14 | open_details | 333.6 | 330.4 | 342.0 | 339.7 |
| 1008 | app_open | 2425.7 | 2940.6 | 2450.1 | 3139.5 |
| 1008 | cold_search | 26319.1 | 28098.0 | 26577.0 | 28115.6 |
| 1008 | snapshot_refresh | 549.6 | 639.5 | 589.1 | 672.6 |
| 1008 | first_fresh_search | 22701.8 | 24245.3 | 22980.9 | 24495.7 |
| 1008 | different_query | 23714.2 | 427.3 | 24447.5 | 443.3 |
| 1008 | repeat_query | 22693.2 | 419.9 | 22939.3 | 436.5 |
| 1008 | sort_title | 22777.5 | 867.2 | 22786.8 | 897.6 |
| 1008 | narrow_type | 9531.0 | 643.5 | 9813.8 | 651.5 |
| 1008 | widen_type | 23128.7 | 663.7 | 24133.2 | 706.6 |
| 1008 | open_details | 643.4 | 834.8 | 674.3 | 961.9 |

Different-query savings: **274.8 ms (81.3%)** for 14 records and **23.287 s
(98.2%)** for 1,008 records. Median encode time fell from 259.4 to 12.3 ms and
23,289.2 to 13.6 ms respectively. This is user-visible improvement, not just an
encoder-only benchmark. Queries are still inferred on repeat submission.

Costs remain visible: large cold search increased from 26.32 to 28.10 seconds,
and first search after refresh from 22.70 to 24.25 seconds. Refresh increased
from 0.55 to 0.64 seconds and details from 0.64 to 0.83 seconds in this sample,
despite no encoding or extra reads for either. Small first-fresh latency also
increased. With two samples, delivery overhead and system variance are not
isolated from packing/async overhead; these are reported costs, not attributed
entirely to one cause. No encoding work was shifted into app open or refresh.
Model initialization medians were 2.50 -> 2.93 seconds on the large trials
(2.71 -> 2.77 seconds on the small trials). Cold passage inference remains slow.

## Cache and responsiveness contract

Each ranker keeps at most **2,048 passage vectors and 8 MiB of vector payload**,
evicting least-recently-used entries. For this model's 384 doubles, the entry
limit caps payload at 6 MiB; 1,008 entries use 3,096,576 bytes. Entry metadata is
also bounded by the entry count. Bounds exclude model weights, the already
loaded snapshot and transient encoding/scoring arrays. A working set larger
than the cap can re-encode evicted passages.

The key includes full scope/UUID and a SHA-256 of title/description. Reuse also
requires the identical authorized record tuple, snapshot token and model
configuration. The controller clears vectors on refresh, logout, expiry and
account changes. Replaced/filtered source snapshots invalidate the cache;
ordinary query filters reuse only eligible vectors and lazily encode newly
eligible passages. Queries/results are not stored in the ranker cache.

Inference runs in a worker, serialized per controller. Query/session/snapshot
checks discard obsolete completions. Clearing the cache advances an epoch;
an old worker cannot repopulate it after invalidation. UI request generations
also discard stale results/errors. The current rendered result is retained only
for its current query/controls/session/snapshot; every new submission infers the
query again. Existing privacy, popover, dialog, focus and scroll behavior remains.

An in-flight ONNX operation is not interrupted; a new query can wait behind it.
Cold searches and post-refresh searches still encode all eligible uncached
passages. Broad scoring/result rendering and dropdown/dialog transitions remain
other costs. No database, cutoff, model, ranking policy, pagination or scheduler
change is part of this optimization.
