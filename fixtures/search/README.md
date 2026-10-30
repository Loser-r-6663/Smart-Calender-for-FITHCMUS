# Representative search fixtures

This dataset enables search development before crawlers and storage are ready:
**40 synthetic tasks, 32 queries, 3 independent change scenarios**. No real student
data, credentials, live sources, embeddings, database migration, or search engine
is included. All source URLs use `https://fixtures.example.invalid/` and must not
be crawled. Course notices, dates, audiences, and points are invented for testing;
they do not describe official FIT-HCMUS requirements.

## Files and verification

Run from the repository root with Python 3.10+ and the standard library only:

```console
python -X utf8 fixtures/search/build_data.py --check
python -X utf8 fixtures/search/validate.py
python -X utf8 -m unittest discover -s tests -v
git diff --check
```

The validator reports counts and checks IDs, fields, timezone-aware dates,
intervals, scenario transitions, expected/excluded IDs, coverage, and hard filters.
It independently audits exact sets using small fixture predicates and whole-token
matching. It never writes expectations and is not the implementation under
evaluation. Mutation tests verify that corrupted fixtures fail validation.
These checks **do not verify retrieval behavior**, index synchronization, query
understanding, ranking quality, or semantic similarity in an application.

`tasks.json`, `queries.json`, and `scenarios.json` are directly consumable UTF-8
artifacts. `build_data.py` is their compact, curated source, including every
manually chosen expectation. To edit, change that source, run
`python -X utf8 fixtures/search/build_data.py`, then run the checks above.
`--check` compares bytes without modifying files. Outputs use UTF-8, preserved
Vietnamese accents, LF newlines, stable ordering, and no clock or random input.
The fixture-local `.gitattributes` preserves JSON LF bytes on Windows checkouts.

## Task contract and schema reuse

Tasks use the 22 field names and enums in
[Suitable Schema for Task](../../Suitable%20Schema%20for%20Task.md).
There is no executable model on the inspected `Search` branch. The validator
therefore checks a fixture subset of that documented contract without adding a
production model or endorsing a new production schema. All 22 keys are present;
unavailable optional values are JSON `null`:

| Group | Fields and fixture rules |
| --- | --- |
| Identity and text | `id`, `title`, `type`, `course_code`, `description`, `target_audience`, `location` |
| Registration | `registration_start`, `registration_end`; optional independently |
| Event interval | `start_time`, `end_time`; when both known, start < end |
| Obligation | `deadline` required for assignment/tuition; `estimated_hours` optional |
| Activity | `training_points` is 0–100; positive points have `drl_category` |
| Lifecycle | `status`, `recurrence`, `is_manual`, `updated_at` |
| Provenance | `source_url`, `source_platform`, `embedding` (always null) |

Fixture IDs are readable lowercase strings of at most 40 characters instead of
generated UUIDs/hashes. Titles obey the stricter documented 255-character table
limit. `type` is one of `class`, `assignment`, `exam`, `event`, `personal`,
`tuition`; status uses `active`, `done`, `archived`, `cancelled`. Sources reuse
`moodle`, `portal`, `facebook`, `custom`. The class fixture represents a single
materialized occurrence; recurrence expansion is outside this dataset.

The parent `algorithms/algorithms-for-task-search-and-retrieval.md` uses older
names (`event_type`, `registration_deadline`, `short_description`, `event_url`).
The repository schema takes precedence here (`type`, `registration_end`,
`description`, `source_url`). That document's prototype permits null registration
bounds and falls back to active records on an empty candidate set. These fixtures
intentionally propose stricter unknown-date and keyword-miss policies below.
The parent `diagram.md` and `report_final.docx` provide context for task management,
distinct date roles, and updates preserving identity; they are not runtime code
or prerequisites to running these checks.

## Clock, date, missing-value, and status policies

The fixed reference clock is **2026-10-30T12:00:00+07:00** (Asia/Ho_Chi_Minh).
Every timestamp, including explicit query overrides and scenario clocks, has a
UTC+07:00 offset. Nothing uses the machine's current date.

- Today means `[2026-10-30T00:00:00+07:00, 2026-10-31T00:00:00+07:00)`.
  Every `*_within` filter uses lower-inclusive, upper-exclusive bounds.
- Events use half-open `[start_time, end_time)` intervals. An overlap requires
  `start_time < query_end AND end_time > query_start`, with both dates known.
  An event from October 29 through 31 overlaps today without starting today.
  Ending exactly at today's midnight or starting exactly at tomorrow's midnight
  does not overlap today. `start_time_within` only inspects the start.
- Registration is definitely open only when **both** bounds are known and
  `registration_start <= reference_time <= registration_end`. Closing is inclusive.
  Missing start, missing end, or both missing means unknown, excluded from
  definitely-open results. Known future starts are excluded too.
- `registration_end_within` asks which registrations close in a date window;
  it does not assert they are still open. Thus q05 includes the 11:00 closure.
- `deadline` means assignment submission or tuition payment; it is never inferred
  from registration or event dates. Null values fail predicates on that field;
  unrelated filters can still match the record.
- Default status is `active`. Explicit `statuses` replaces that default, allowing
  done, archived, or cancelled results. Passage of time does not change status;
  an overdue active assignment stays active. Deletion removes the record entirely.

## Query contract and expectation policy

Every query has a stable `id`, human-readable `text`, `mode`, `evaluation`,
`state`, `reference_time`, canonical `request`, expected IDs or relevance labels,
`excluded_ids`, `ordering_required`, `rationale`, and `coverage_tags`.
Exclusions may name a deleted base ID to assert that it cannot return.

All 32 queries evaluate **retrieval**: feed the provided `request` to a future
adapter, rather than parsing `text` and conflating parser mistakes with retrieval
mistakes. The text documents intent. Query-understanding tests can later use the
text/request pairs as parser targets, but no parser is exercised here.

| Request field | Meaning |
| --- | --- |
| `filters.course_code` | Exact course equality; semantic similarity cannot override it |
| `types`, `statuses` | Allowed enum values (nonempty lists) |
| `source_platform`, `target_audience` | Exact stored value |
| `location_prefix` | Literal case-sensitive prefix |
| `min_training_points` | Inclusive lower bound |
| `registration_open_at` | Inclusive point test with both endpoints known |
| `registration_end_within`, `deadline_within`, `start_time_within` | Half-open range on the named field |
| `event_overlaps` | Half-open interval intersection |
| `keyword` | Whole-token AND over title, description, audience, and location |
| `semantic_text` | Intent requiring manual graded judgments |

Filter fields live inside `request.filters`; keyword/semantic text are alongside
that object. All supplied filters combine with AND. Query modes are `structured`
(filters only), `keyword` (lexical, optionally with status filters), `semantic`
(intent with hard filters), and `hybrid` (lexical request plus hard filters).
Hybrid cases here do not request a vector branch or specify fusion weights.

For deterministic lexical expectations, casefold, map Vietnamese `đ` to `d`,
decompose Unicode to NFD, remove combining marks, then split into `[a-z0-9]+`
tokens. All query tokens must occur in the combined searchable fields. This
matches composed/decomposed Vietnamese and `học phí`/`hoc phi`; it does not
translate tuition into Vietnamese, stem words, or match partial course codes.
Course identity comes from the explicit filter, not similarity or substring
matching. Empty matches remain empty, with **no unrelated active-task fallback**.

Thirty queries use manually specified, exhaustive `expected_ids` sets. Compare
sets after collecting all results (the fixture has no pagination/truncation).
All queries have `ordering_required: false`; array order is serialization only.
The remaining two semantic queries use grades **2 = directly relevant,
1 = related, 0 = irrelevant**. `unlisted_eligible_grade: 0` makes judgments
exhaustive over the hard-filter-eligible pool; ineligible records must never be
returned. There are no invented model scores or precise rank requirements:

- q21: `evt-green` (campus litter collection and planting) and `evt-beach`
  (coastal litter collection) both directly serve environmental volunteering (2).
  Other eligible events concern unrelated activities (0).
- q22: `evt-speaking` directly practices presentations with feedback (2);
  `evt-debate` practices related argument and communication skills (1).
  They are the only K26 event records in the fixture.

These manual labels are development judgments, not a statistically representative
benchmark. The synthetic wording and small size limit generalization.

## Scenario application

Each scenario forks the complete `base` task set independently; do not apply them
in sequence. Evaluate `before_queries` on base. Then copy base, find `task_id`,
apply `changes` for an update or remove the record for a delete, and evaluate
`after_queries` on that scenario's state. Changes preserve ID and unrelated fields,
advance `updated_at` to the fixed clock, and leave unrelated records unchanged.

| State | Operation | Before → after query IDs |
| --- | --- | --- |
| `edited` | `asg-update`: Bản nháp đồ án → Final retrieval report; due October 30 → November 2 | q25/q27 → q26/q28 |
| `cancelled` | `evt-cancel`: active → cancelled | q29 → q30 |
| `deleted` | Remove `evt-delete` | q31 → q32 |

Updates must replace indexed content for the existing ID. Cancellation removes
default visibility; explicit status selection can still expose the record.
Deletion removes it from all result sources. The explicit delete operation is
assumed authoritative; a crawler failure alone is not evidence of deletion.

## Coverage and future integration

The [structured search service](../../docs/structured-search.md) now exercises all
nine existing structured-query expectations through an in-memory SQLite adapter.
The standalone validator above still checks fixture integrity independently.
Keyword, hybrid and semantic retrieval remain future integration work.

| Required case | Query IDs / supporting records |
| --- | --- |
| CSC10004 versus CSC10005 | q01–q02, q18, q23; paired labs and projects |
| Accented/unaccented tuition | q03–q04 |
| Registration closes today; before/exact/after | q05–q08; 11:00, 12:00, 13:00 closures |
| Overlap versus starts-within and midnight | q09–q10; October 29–31 and touching-midnight records |
| Missing registration endpoints | q11–q13 |
| Default and explicit statuses | q14–q16, q24; overdue-active q01 |
| Empty keyword results | q17–q18 |
| Title/deadline change, cancellation, deletion | q25–q32 |
| Tuition, points, audience, source, combined filters | q19–q23 |
| English/Vietnamese/mixed language, semantic intent | q02–q04, q21–q22 and multilingual task text |

A future search adapter must map this fixture request vocabulary to its actual
interface, load each isolated state, compare exact sets, enforce hard filters on
semantic results, and evaluate graded relevance without treating IDs as a ranking.
Index updates, deletion propagation, parser output, retrieval performance, and
ranking need application integration tests once executable interfaces exist.
