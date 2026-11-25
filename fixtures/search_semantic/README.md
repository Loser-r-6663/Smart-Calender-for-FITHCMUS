# Vietnamese keyword retrieval baseline

This is an offline measurement over fictional records, not a semantic-search implementation or evidence of deployed database permissions. It uses the existing `academic_search.search_records()` matcher, including the uncommitted `nhiều hơn` and `bé hơn` aliases.

From the repository root, using the existing project environment:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.run_keyword --check
```

The command recomputes every result and compares the per-query ordering and aggregate measurements with [keyword_baseline.json](keyword_baseline.json). It exits nonzero for changed inputs/report or a correctness violation. A relevant paraphrase missed by keywords is a measured retrieval miss and does not make this baseline invalid. Unrelated-query false hits are also measured independently of control failures.

To write a separate measured report without changing any labels:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.run_keyword --output "$env:TEMP\keyword-measurement.json"
```

## Frozen inputs and scoring

- [corpus.json](corpus.json) contains 14 valid task objects and fictional guest/account A/account B identities. A housing-payment notice is a plausible distractor for the tuition deadline paraphrase. Public and personal tasks can share a UUID; A and B also have distinct personal records with the same scoped UUID.
- [cases.json](cases.json) contains 31 authored cases. Every case records its ID, Vietnamese query, viewing account, disabled sources, selected filters, sort, relevant `(scope, UUID)` keys (including explicit empty answers), split, scoring kind, and factual rationale. Answers and the tuning/held-out split were written before measuring the matcher. Author review included both environmental activities as relevant before the first run. No labels were revised after observing scores.
- [frozen_inputs.json](frozen_inputs.json) pins the corpus and cases. Fingerprints normalize only CRLF to LF so a Windows Git checkout preserves the freeze. Other edits fail before matcher execution. Version 1 labels, corpus and splits must remain unchanged for the later keyword/hybrid comparison; introduce a separate evaluation version for new judgments.
- For each case, public tasks plus the current fictional owner's personal tasks are selected, then disabled sources are removed. Only that tuple is supplied to `search_records()`. This fixture projection is not an implementation of production authentication or database policy.
- The report stores each case's expected keys, actual ordered top three, total hit/eligible counts, and expected-key positions. Only `kind=paraphrase` cases enter the paraphrase denominator: a success means at least one expected relevant key occurs in the top three. Exact controls, visibility checks, point/structured filters and unrelated queries are excluded from that denominator.
- Unrelated-query false positives count any returned hit, with case IDs reported by split. Visibility, point-filter and strict-boundary violations are recorded separately from retrieval misses. Exact/visibility/point/structured control results must match their authored answer sets. In particular, a strong topical five-point task is forbidden by both strict five-point comparisons; zero is known and unknown points never satisfy a comparison.

## Recorded keyword measurement

Measured on 25 November 2026 with project Python 3.12.14 on `search-supabase-ui` at `c6cae06` plus the existing two alias edits. The report pins the matcher source's LF-normalized SHA-256, so changing the keyword implementation cannot silently reuse this report.

| Split | Answerable paraphrases found in top three | Unrelated queries with false hits |
| --- | --- | --- |
| Tuning | 1 / 3 | 0 / 2 |
| Held-out | 0 / 4 | 0 / 2 |

No unrelated query returned a hit: **0 / 4 overall**. There were zero visibility, point-filter, strict-boundary, or control violations. The three exact controls, eight visibility checks, eight point controls and one combined structured-filter case passed. Empty paraphrase results remain in the report as baseline evidence.

Generation and verification ran in separate Python processes with identical frozen inputs; a second run matched every per-query key order and aggregate byte-for-byte. The regression tests additionally generate reports in two independent processes and compare them. No model, embedding dependency, database, crawler or server is needed. Later retrieval evaluation can reuse `load_inputs()`, `visible_records()` and `evaluate(matcher=...)` against the same task objects and cases; expected answers must not be derived from model output.
