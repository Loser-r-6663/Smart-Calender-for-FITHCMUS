# Vietnamese Search evaluation

All records and queries here are fictional. The pinned model and cutoff are
unchanged. Historical pilot, calibration, repair and replay
artifacts remain recoverable from **`0acb8e6256c81d52d5bf5b18bb4fa83b61669e0c`**;
they are not copied into a second archive.

## Current commands (repository root)

Fast core tests, without a model or database:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
Remove-Item Env:SEARCH_SEMANTIC_MODEL -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -q -m search_core
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.run_keyword --check
```

The single fictional demo is `python -m fixtures.search_demo.app`; follow the
Vietnamese steps in [CLIENT_GUIDE.md](../../CLIENT_GUIDE.md#7-demo-search-trên-bản-tích-hợp).
The actual browser journeys are `python -m pytest -q -m search_browser`.
See [verification and coverage](../search_demo/VERIFICATION.md) for ownership,
consolidation decisions, observed results and remaining limitations.

### Optional local model

`intfloat/multilingual-e5-small`, immutable revision
`fd1525a9fd15316a2d503bf26ab031a61d056e98`, MIT license, cutoff **0.86**.
CPU ONNX Runtime uses masked mean pooling, normalized cosine similarity,
`query:`/`passage:` prefixes and a 512-token limit. Vietnamese is supported.
Weights/tokenizer/model card total **487,848,778 bytes**, plus the 42-byte
revision marker. Query/task inference stays on the machine. Weights belong
outside Git; keyword users need neither these dependencies nor model assets.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.setup_model "$env:LOCALAPPDATA\SmartCalendar\models\multilingual-e5-small"
$env:SEARCH_SEMANTIC_MODEL = "$env:LOCALAPPDATA\SmartCalendar\models\multilingual-e5-small"
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.run_hybrid --check --output "$env:TEMP\search-quality.json"
```

Setup downloads public assets only; inference never downloads anything. Missing
files/dependencies or failed inference preserve keyword membership and ordering.
The quality command evaluates the current ranker both unprepared and explicitly
prepared, requiring **all 31 complete ordered result sets** to agree with each
other and [the retained expected report](hybrid_integrated_report.json).
It is regression verification on previously inspected cases, not blind evaluation
or calibration. Outputs go to TEMP, never over frozen/retained evidence.

## Frozen inputs and scoring

- [corpus.json](corpus.json): 14 valid fictional tasks, guest/account A/account B;
  different accounts can hold different text under the same scoped UUID.
- [cases.json](cases.json): 31 authored queries with identities/source preferences,
  filters, expected full keys, explicit empty answers, rationale and tuning/held-out
  splits. Judgments were written before observing retrieval; no relabeling or tuning.
- [frozen_inputs.json](frozen_inputs.json): source guards normalize CRLF to LF only.
  Any other input change fails before matching. [keyword_baseline.json](keyword_baseline.json)
  also fingerprints matcher source; its reviewed `personal`-type source update
  preserved every other field and did not change ranking. The subsequent event-only
  point-comparison update also preserved every frozen outcome and aggregate;
  only the reviewed matcher fingerprint changed. Current source digest:
  `ebe75d1b825a49784470482ab47c1c2639f5c2f73e381cd8f4a3890310680103`.
- Only authorized, source-enabled records reach the matcher/ranker. Topic
  interpretation and structured filters run first; semantic retrieval uses the
  remaining topic and all eligible records. Literal hits survive; exact eligible
  title/course queries suppress semantic-only expansion. Explicit sorts and scoped
  ties apply unchanged. Blank/point-only searches skip inference.
- Only answerable paraphrases enter the top-three denominator. Exact/visibility/
  structured/point controls are correctness checks, unrelated queries measure false
  hits separately, and keyword paraphrase misses are valid baseline evidence.

| Method | Tuning paraphrases | Held-out paraphrases | Unrelated false hits | Correctness violations |
| --- | --- | --- | --- | --- |
| Keyword | 1/3 | 0/4 | 0/4 | 0 |
| Pinned local model | 3/3 | 1/4 | 0/4 | 0 |

Expected keys, top-three positions and complete hybrid ordering remain in the two
retained reports. Model-unavailable fallback over all frozen cases remains a fast
core check. These fixtures do not prove deployed database permissions.

## Current performance command

Run separately from pytest/other inference. Same P workloads: 14 frozen task facts
projected into one mock owner, and 72 indexed repetitions = 1,008 records with
stable UUID5 identities. `tasks()` now lives in the runner itself. No database,
accounts, scheduling or task writes are used.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.preparation_benchmark --warm-queries --check --output "$env:TEMP\search-performance.json"
```

The actual Edge popover runs early-literal, early-paraphrase and prepared searches
in fresh app/controller/browser processes. It separates calendar readiness,
preparation, preliminary feedback, final results, encoding counts and task reads.
A different and repeated warm query are measured too. `--check` compares complete
ordered keys against [preparation_integrated.json](preparation_integrated.json),
requires no search/detail task reads and no prepared-query passage encoding.
Timings are observations, never pass/fail thresholds. One trial per scenario;
not a median, SLA or cold-disk benchmark. Calendar-ready excludes real sign-in.

Historical integrated-build observations in that report: first prepared results
112/325 ms (14/1,008), different warmed query 78/403 ms, zero passages/task reads.
Preparation 4.493/23.063 s; early 1,008-record final results about 25 s. Current
cleanup reruns are reported separately in the verification summary.

The controller prepares small batches after first paint, yielding between batches
to foreground queries. Cache limits remain 2,048 entries / 8 MiB vector payload;
384 doubles use 3,072 bytes each (maximum 6 MiB at the entry bound). Model weights,
metadata and temporary arrays are additional. Preparation stops partial at capacity
without eviction churn; foreground retrieval uses the existing LRU. Snapshot,
text, source and session changes invalidate cache epochs; old work cannot republish.
Preliminary rows stay usable with neutral `Searching…`; only completed successful
empty retrieval shows `No matching tasks`. No inferred point-summary labels.

## Retired dependencies

`check_prepared.py` previously executed captured source from
`preparation_reference.json` and read `hybrid_performance_report.json`. Both
inputs and that runner retire together; current `run_hybrid --check` compares
prepared/unprepared current results against the retained complete expected keys.
The old `benchmark.py` before/after replay and `compare_latency.py` /
`compare_preparation.py` are historical experiments; their pilot/intermediate
JSONs and three overlapping prose guides retire together. Current measurements
use only `preparation_benchmark.py` and the retained integrated report.

Inspect historical evidence without restoring it into the working tree:

```powershell
git show 0acb8e6:fixtures/search_semantic/preparation_reference.json
git show 0acb8e6:fixtures/search_semantic/hybrid_calibration.json
```
