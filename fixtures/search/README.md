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

## Dataset contract and database compatibility

The dataset retains the earlier 22-field shape from
[Suitable Schema for Task](../../Suitable%20Schema%20for%20Task.md).
It is test data, not a set of valid current database task payloads. The agreed
[`Database/task_schema.json`](https://github.com/Loser-r-6663/Smart-Calender-for-FITHCMUS/blob/7aa63cfc5453a70a12b73b099c4f56e1dc583825/Database/task_schema.json)
reference is Database commit `7aa63cfc5453a70a12b73b099c4f56e1dc583825`, verified
against GitHub on 2026-11-07. The
[Search integration documentation](../../docs/structured-search.md#current-database-task-payload-contract)
records the full task contract and disagreements among JSON Schema, Python and SQL.

| Fixture value or rule | Difference from the current database contract |
| --- | --- |
| All records contain `course_code` and `embedding: null` | Both are forbidden extra task properties; the database uses nullable free-text `course` and has no `embedding` field |
| `course_code` values and `filters.course_code` are exact course codes | A test mapping to `course` is possible for these controlled values, but arbitrary production course names/text do not preserve exact code identity by renaming alone |
| `recurrence` is `NONE`, or `WEEKLY:FRI` for `class-csc10004` | Neither matches the database weekday/time format, e.g. `T2 08:00-10:00`, or null; every unchanged fixture fails the schema recurrence pattern |
| IDs match `[a-z0-9-]{1,40}` | A valid subset of the database's 1–64 character nonblank strings; UUIDs are not required by the payload schema |
| All 22 keys, including nullable keys, are present | The database permits 21 fields; only ID/title/type are always required, with deadline additionally required for assignment/tuition |
| Base JSON points are integers 0–100; positive points include a category | These values match the points rules. Null-point variants added by Search tests are accepted by the SQLite adapter but rejected by the database schema/model/SQL |
| Aware timestamp strings use UTC+07:00 | Valid database timestamp inputs; the fixture validator is narrower than the database, which permits other explicit offsets. PostgreSQL returns instants, not original timestamp strings |

The dataset covers all six types: `class`, `assignment`, `exam`, `event`,
`personal`, `tuition`. Status values are `active`, `done`, `archived`, `cancelled`;
source platforms are `moodle`, `portal`, `facebook`, `custom`. These enums agree
with the current database. Titles are 2–255 characters. Optional date endpoints
are independent, known interval endpoints are ordered, and assignment/tuition
have deadlines. The class is one materialized occurrence; recurrence expansion
is outside this dataset.

`validate.py` checks this fixture contract, not `task_schema.json`. Passing it does
not prove database compatibility. A future PostgreSQL test adapter needs explicit
field and recurrence mappings that preserve each expectation; it must not send
these records unchanged to database creation. Production searches query database
state directly and require no JSON-to-SQLite import.

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
| `filters.course_code` | Exact fixture code equality; semantic similarity cannot override it |
| `types`, `statuses` | Allowed enum values (nonempty lists); omitted types means all six, omitted statuses means active |
| `source_platform`, `target_audience` | Exact stored value |
| `location_prefix` | Literal case-sensitive prefix |
| `min_training_points` | Inclusive lower bound |
| `registration_open_at` | Inclusive point test with both endpoints known |
| `registration_end_within`, `deadline_within`, `start_time_within` | Half-open range on the named field |
| `event_overlaps` | Half-open interval intersection |
| `keyword` | Whole-token AND over title, description, audience, and location |
| `semantic_text` | Intent requiring manual graded judgments |

Filter fields live inside `request.filters`; keyword/semantic text are alongside
that object. Filter names are not task properties: `min_training_points` is an
inclusive bound over the `training_points` task field. All supplied filters combine
with AND. Query modes are `structured`
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

The explicit `academic_search.sqlite_service.SearchService` exercises all nine
existing structured-query expectations through an in-memory SQLite adapter. The
[production search service](../../docs/structured-search.md) queries PostgreSQL
through the selected DatabaseManager and does not import this dataset.
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
