# Search verification and consolidation

Reference: **Commit 7 `0acb8e6256c81d52d5bf5b18bb4fa83b61669e0c`**, `FE-Client`.
This cleanup changes tests, runners and docs only. Search/client/database/scheduler
runtime, model revision/cutoff, frozen judgments and expected results are unchanged.

## One core command; one fictional demo

From the repository root in the existing project environment:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
Remove-Item Env:SEARCH_SEMANTIC_MODEL -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -q -m search_core
```

Core selection launches no browser/model or network request. Collection uses the
project's installed test dependencies. Actual fictional browser journeys:
`python -m pytest -q -m search_browser`; the full repository command is unchanged,
`python -m pytest -q`. Use a fresh writable `--basetemp` for repeat verification.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_demo.app
```

Open `http://127.0.0.1:8091/login` in a private window; mock login `student/demo`.
The fixed **15 fictional tasks** support both exact/points/details/local-source
and CSC10006 inclusive-week sorting. See [Vietnamese walkthrough](../../CLIENT_GUIDE.md#7-demo-search-trên-bản-tích-hợp).
Setting the optional local model before the same command enables paraphrases.
[Current quality/performance commands](../search_semantic/README.md) write new
observations to TEMP instead of adding report files here. No live sign-in is
required or performed for cleanup.

## Inventory and ownership

Comparable counts include surviving tracked files and new nonignored working
files, excluding deleted/ignored/generated output. Test modules are files,
not parametrized cases or unittest subtests.

| Inventory | Commit 7 | Working cleanup |
| --- | ---: | ---: |
| All files in `tests/` | 37 | 33 |
| Search-owned test modules | 18 | 13 |
| Files in `fixtures/search_demo/` | 13 | 4 |
| Files in `fixtures/search_semantic/` | 39 | 11 |

Search ownership: `test_search_*`, former compact/independent/semantic UI modules,
`test_task_detail_fonts.py`, `test_task_retention.py`, `test_task_retention_ui.py`.
The nine fast modules are records, loader, matcher, semantic, baseline, client
state, embedding cache, preparation, and task retention. Four browser modules
are main UI, async UI, detail fonts, and task retention UI. `search_ui_support.py`
is shared harness/fixtures, not a test module. `test_search_ui` reexports its
existing helper names so FE tests remain independently runnable. The other
18 test modules, including FE/shared merge, auth, crawler and scheduler, remain
byte-identical. No CI configuration referenced the retired files.

## Removal map

The 256-case collection becomes **234**: **32 former IDs replaced/removed, 10
new IDs**, net -22. All removed IDs were checked against this map; unrelated
case IDs are unchanged. All **512** grammar/boundary subtests remain.

| Retired check(s) | Reason | Surviving coverage |
| --- | --- | --- |
| `test_compact_search_ui` desktop/narrow closed/open workflow | duplicate | Main `test_idle_submission_independent_filters_and_clear` checks toolbar geometry, idle, focus, Escape and independent controls; narrow scroll journey checks viewport bounds |
| `test_independent_search_ui` both journeys | covered elsewhere | Both named functions retained in `test_search_ui`; Personal/Assignments journey also checks all five row badge labels/colors |
| `test_search_feedback_ui` badge journey ×2 widths | duplicate | Five row styles in Personal/Assignments; Class row/dialog style equality in `test_open_scoped_details_sources_occurrences_and_refresh`; other scoped details/source facts retained there |
| `test_search_feedback_ui` pending/empty/failure ×2 widths | covered elsewhere | `test_search_async_ui.test_pending_empty_and_failure_feedback_is_neutral`: preliminary upgrade, neutral count/sort, successful empty versus failed fallback, loading/expiry/service feedback |
| `test_search_preliminary_ui` public/personal opener variants | duplicate | Private UUID-collision opener survives final upgrade with source/focus in async journey; public/private original selection remains in scoped-details journey |
| `test_search_preliminary_ui` zero literal, Clear and final | covered elsewhere | Same async journey checks zero-overlap retrieval/details, no premature empty state, Clear during pending work and final empty |
| `test_semantic_ui` ordinary semantic details | duplicate | Async zero-overlap result → original/source/focus/no extra reads |
| `test_semantic_ui` pending account switch | covered elsewhere | Named `test_pending_inference_keeps_ui_responsive_and_discards_old_account` retained in async module |
| `test_search_demo` missing-model frozen check | duplicate | `test_search_semantic.test_unavailable_fallback_is_frozen_keyword_baseline` already compares the entire 31-case report |
| `test_search_demo` course/week ×2 widths, separate `verify_ui` runner | duplicate | Main `test_documented_demo_exact_points_course_week_and_source` launches the actual documented module; login, exact lookup, point boundary, inclusive week, three ordered key lists, original/source and keyboard return |
| Main `test_real_search_controls_and_ordering` long grammar/sort replay | covered elsewhere | Matcher tests retain every grammar form, structured filter, literal/topic and sort membership; demo tests UI point boundary/course sorting; idle journey corrects filter errors |
| Main seven `test_effective_point_bounds_remain_available` empty-record checks | duplicate | Matcher phrase table and `test_strict_and_inclusive_intersections_with_selected_bounds` assert full effective filters on real fictional records, including conflicts/domain edges |
| Main date endpoint test and three invalid-source cases | covered elsewhere | Same named checks moved to fast `test_search_records` |
| Main `test_narrow_layout_navigation_and_feedback` | duplicate | Scoped-details journey covers Calendar/Agenda selection, async covers feedback, narrow dialog covers scrolling/focus/controls |
| Main `test_personal_and_assignments_controls_open_original_scoped_details` | duplicate | Independent Personal versus Calendar Assignments; demo Search Assignments; scoped-details plus three stale-browser transitions and fast session tests |
| Main desktop duplicate of long dialog-scroll case | duplicate | Narrow case keeps unchanged one-pixel page/list/menu bounds, pointer + Enter, Close + Escape, visible long content and restored result focus; desktop source/focus checked elsewhere |

Actual coverage reduction: fewer repeated viewport/alias/opener workflows; no
longer opening every badge type's dialog at both widths. All five row colors and
one shared renderer's dialog-style equality remain, plus scoped originals. The
standalone real-model demo replay is retired; actual-model quality/performance
runners and controlled semantic UI journeys remain independently verifiable.
No distinct required matching/authorization/cache/focus behavior was removed.

## Artifacts and historical evidence

Demo keeps only `app.py`, `tasks.json`, `__init__.py` and this summary. The five
`live_accounts_*_probe.json` files, final/public/UI JSON reports and redundant
browser replay are retired. Commit 7 contains them, without a second archive:

```powershell
git show 0acb8e6:fixtures/search_demo/live_accounts_projection_probe.json
git show 0acb8e6:fixtures/search_demo/live_accounts_verification.json
```

Historical directly observed live evidence at runtime `5ad961d`: guest/A/B saw
23 public rows (guest via repository, not the sign-in-only Calendar), A had
12 private rows and opened its original/source, B and guest
could not retrieve that key, logout dismissed private details/stale callbacks
and cleared caches, and queries/details added zero task reads. B had **zero**
private rows, matching its authenticated export view, so reverse-direction
private ownership had no fixture. No live task was created or changed.

History: an overstrict probe expected an owner column omitted by the state
projection; the corrected harness retained request token/owner checks. Later
navigation timeout/control-request errors were recorded; their cause was not
conclusively diagnosed, and no production fix was claimed. Final verification
used separate fresh control HTTP connections and passed. Sessions ended with
local sign-out 204/204, temporary client/storage removed, no private screenshots,
credentials, task text/IDs/URLs in evidence. **These are historical observations,
not new live checks in T.** Long layout review, Hien shared-build confirmation
and unseen teammate paraphrase feedback remain pending.

**Obsolete/superseded artifacts:** pilot/intermediate/replay and calibration
history retire from the active tree, not from Git. No testcase was dropped
as obsolete; test reductions above are duplicates or retained elsewhere.

Semantic keeps frozen corpus/cases/splits/manifest/keyword baseline, model setup,
current quality runner + complete expected report, current performance runner +
measurement, and one README. Retired pilot/intermediate/replay inputs, calibration
history and three overlapping guides are at the same historical SHA. In particular
`check_prepared` and its captured-source dependency retire together; current
quality checks prepared/unprepared results against the preserved full ordering.

## Cleanup verification (27 November 2026)

- Collection: 256 before, 234 after. Core: **116 passed + 512 subtests**,
  118 deselected, **10.80 s**; initial consolidated browser selection:
  **15 passed**, 219 deselected, **203.99 s**. No failure/error/skip.
- Frozen keyword check unchanged: **1/3 tuning, 0/4 held-out, 0/4 unrelated false
  hits, zero violations**; model regression: **3/3, 1/4, 0/4, zero violations**,
  all 31 complete orders match prepared/unprepared and saved expected results.
- The revised quality command passed with the real pinned model: startup **2.843 s**,
  evaluation **11.861 s**. Outputs are `$env:TEMP/t-quality.json` and
  `t-performance.json`; retained expected JSON files were not overwritten.
- The revised benchmark's six scenarios passed complete-key/read/cache checks.
  Newly observed prepared first results: **213/374 ms** for 14/1,008 records;
  different warm query **102/390 ms**, repeat **90/370 ms**, each zero passage
  encodings/task reads. Early 1,008-record final results **22.857/22.157 s**
  (literal/paraphrase); preparation of the prepared snapshot **4.532/27.881 s**.
  These are new single observations, not an optimization or a timing threshold;
  historical values remain in the retained integrated report.
- The documented app was launched by the surviving browser journey from repo
  root: fictional login, exact/points → source, and course/week → three sorts →
  original details passed. A separate manual Playwright execution with the real
  model also verified the zero-literal tuition paraphrase at **rank 1** (keyword
  empty), source destination and Clear at **1280×900 / 390×844**. Desktop popover
  and narrow dialog screenshots were inspected; generated output stayed in TEMP.
- Final independent-controls follow-up after retaining Best match/course-choice/
  zero-point row assertions: **2 passed, 32.68 s**. Full suite before the final shared badge-style strengthening passed **234 tests +
  512 subtests in 229.19 s**. The **final full suite** (including all five white
  badge foregrounds and Class row/dialog background, foreground, font metrics,
  padding and radius equality) passed **234 tests + 512 subtests in 220.35 s**,
  **0 failures, 0 errors, 0 skips**, with the same 48 inherited Pydantic warnings.
  JUnit counts 746 including subtests; logs: `$env:TEMP/t-final.txt` / `.xml`.
  Used the project Python 3.12.14, pytest 9.2.0, NiceGUI 3.19.0, Playwright 1.65.2,
  Edge 158.0.4370.33, CPU ONNX 1.23.2, pinned model/0.86 cutoff unchanged.
  `PYTHON_DOTENV_DISABLED=1`, model unset for pytest, fresh writable `--basetemp`,
  `-p no:cacheprovider`; no skips/xfails/retries or relaxed assertions.
- No live credentials/accounts, crawler, scheduler or operational `server.py` used.
  Model assets already installed outside Git; no package/model download needed.

Final import/link/whitespace and inventory review passed; all 18 unrelated test
modules/case IDs and all production runtime bytes are intact. Six retained frozen/
expected JSONs are byte-identical. New checks do not duplicate an archive; history
is in Git at the reference SHA. Work remains unstaged, without commit/push/PR.
**Ready to commit: Yes** — required cleanup checks passed; historical B-fixture,
review and single-observation latency limitations above remain explicit.
