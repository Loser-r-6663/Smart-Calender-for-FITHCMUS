# Optional local Vietnamese retrieval

The keyword matcher and Commit E's frozen inputs/report remain unchanged.
`academic_search.semantic.HybridSearch` filters through that matcher first,
then combines literal hits with local title/description embeddings. Exact
title/course topics keep the complete keyword result set without semantic-only
expansion, using only authorized, filter-eligible records for this decision.
Other topic queries retain hybrid retrieval. Explicit sorts apply to the combined
set. Only the parsed topic is embedded; blank and point-only queries skip the
model. No repository or SQLite read is performed by ranking or detail selection.

Model: [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small/tree/fd1525a9fd15316a2d503bf26ab031a61d056e98),
immutable revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`, MIT license.
The pinned model card lists Vietnamese. Inference uses CPU ONNX Runtime,
masked mean pooling and normalized cosine similarity, with E5's `query:` and
`passage:` prefixes, truncating at 512 tokens. Only title/description are embedded.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.setup_model "$env:LOCALAPPDATA\SmartCalendar\models\multilingual-e5-small"
$env:SEARCH_SEMANTIC_MODEL = "$env:LOCALAPPDATA\SmartCalendar\models\multilingual-e5-small"
$env:PYTHON_DOTENV_DISABLED = '1'
$env:CLIENT_MODE = 'mock'
.\.venv\Scripts\python.exe -B -X utf8 -m client.main
```

Setup downloads public model assets only. Normal Search never downloads files,
contacts an inference endpoint, or sends queries/tasks off the machine. Omit the
optional requirements and environment variable for unchanged keyword search.
Missing files/dependencies or inference failure preserve keyword results and
ordering; diagnostics include exception type only. Remove the variable to
disable semantics. No model weights belong in Git.

The controller holds weights only, with no cached task/query vectors or results.
Each call embeds only the current authorized, source-enabled, filtered snapshot.
This intentionally avoids stale private caches across refresh/account changes.
Inference is synchronous, so it has no background completion that could publish
after a session change. Large snapshots may block UI processing during inference;
further latency work is separate.

Reproduce calibration **before** evaluating held-out cases:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.run_hybrid --calibrate --output fixtures/search_semantic/hybrid_calibration.json
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.run_hybrid --output fixtures/search_semantic/hybrid_report.json
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.run_keyword --check
```

Calibration reads only tuning case outcomes, searching cutoffs 0.750–0.950 in
0.005 increments. It requires no tuning false positives/control violations,
maximizes paraphrase top-three hits, then selects the higher cutoff on ties.
The selected cutoff must be frozen in `semantic.CUTOFF` before the held-out run.
Reports keep keyword/hybrid top-three keys and expected positions side by side.
No labels or split assignments may be changed in response to results.

Model startup timing includes tokenizer/ONNX session creation. Warm query timing
includes fresh title/description and query encoding, filtering and combination,
not database access. See the measured reports and roadmap for actual byte sizes,
device, timings, results and any unmet acceptance condition.

## Measured result (26 November 2026)

Downloaded assets total **487,848,778 bytes**: ONNX weights 470,268,510,
tokenizer 17,082,730 and model card 497,538. They are stored outside the repo
under the configured local application-data directory. No GPU is required.

The tuning-selected cutoff is **0.86**. It was frozen before the held-out run.

| Split | Keyword paraphrases top three | Hybrid paraphrases top three |
| --- | --- | --- |
| Tuning | 1/3 | 3/3 |
| Held-out | 0/4 | 1/4 |

All four unrelated queries remained empty. All expected paraphrase hits occurred
at position 1. T-P01 and T-P02 changed from misses to hits; T-P03 remained a hit.
H-P04 changed from a miss to a hit; H-P01, H-P02 and H-P03 remained misses.
Full scoped keys, top threes and expected positions are in `hybrid_report.json`.

**Not ready to commit:** the frozen evaluator reports two control violations,
H-X02 and H-V05. The expected exact-title hit stays first, but two additional
above-cutoff semantic records are returned. Visibility/ownership, point and
strict-boundary violations are zero. These held-out findings were not used to
retune the cutoff or labels. The evaluation command exits nonzero for these
violations; a green offline implementation suite does not override them.

On the demo CPU (Intel64 Family 6 Model 142 Stepping 11), model startup including
imports/tokenizer/ONNX session took **6.172 s**. All 31 cases over the 14-record
corpus took **11.975 s**. A warm T-P01 query including fresh document and query
encoding took **0.358 s**. There are no task-vector/result cache hits in this
timing. These numbers are not large-snapshot performance claims.

The actual model also retrieved T-P01 through the mock NiceGUI popover, opened
the original scoped details, restored result focus and made no additional task
reads. `tests/test_semantic_ui.py` separately uses a deterministic fake encoder
to verify UI integration and account clearing. Offline control-flow tests are
not evidence of model retrieval quality.

## Post-repair regression verification

The original failed `hybrid_report.json` and calibration report remain intact.
The authorized exact-topic rule suppresses semantic-only expansion when the
matcher finds a full title or full course-code match among eligible records.
It retains every literal hit and the requested order. Ineligible/unauthorized
exact matches cannot suppress ordinary hybrid retrieval.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.run_hybrid --output fixtures/search_semantic/hybrid_repair_report.json
```

With the same pinned revision and cutoff **0.86**, this regression verification
returns evaluator exit **0**, **3/3 tuning**, **1/4 held-out**, **0/4 unrelated
false hits** and **zero correctness violations**. H-X02 and H-V05 each return
exactly `public:33333333-3333-4333-8333-333333333333`, in position 1, with no extra
hits. This is not a fresh blind held-out evaluation: the prior failures were
already inspected before the general exact-match rule was requested.
The original measurements above remain historical evidence, not current failures.

The final keyword-only offline suite after browser lifecycle/scroll repairs passed
203 tests and 512 subtests, with zero failures/errors/skips. The affected browser
cases and their neighboring refresh/details flow also passed three independent
process runs. See the dated repair follow-up in the roadmap for commands,
intermediate failures, event-boundary diagnostics and remaining limitations.
