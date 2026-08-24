# P9-B Gold Governance & Executable Benchmark — Code Review

Date: 2026-08-24 (Asia/Shanghai)

## Review boundary

This second-pass diff review covers migration `20260824_0014`, Gold responsibility contracts,
blind review/import/freeze tooling, canonical truth hashing, Benchmark calculations, PostgreSQL
guards, split/metric contract files and the Slice verifier. It is engineering review only: it is
not independent annotation, adjudication, Gold acceptance or Release Qualification.

The environment did not authorize a separate review agent. No Codex/model identity is represented
as an accountable human role.

## Findings resolved before commit

| Original severity | Finding | Resolution and regression evidence |
| --- | --- | --- |
| P1 | A `human:*` string alone did not establish where the accountable identity assignment came from. | Every one of the four roles now requires an attestation reference in Pydantic, JSON Schema and PostgreSQL. The real importer rejects synthetic references. |
| P1 | The first freeze path had no required blind-end audit record. | Curator freeze now records a specific immutable answer-access event, and the database rejects Gold truth without the event at the exact freeze time. |
| P1 | A later Gold truth version could reuse the original task and its already-visible submissions. | Each task is limited to one truth; version `n+1` must supersede a predecessor from a different, new independently reviewed task. |
| P1 | Evidence summary originally counted all stored truth rows, including low-level synthetic persistence fixtures. | Summary classification excludes any task carrying a synthetic attestation; a PostgreSQL test proves the synthetic frozen row reports `0 / NOT_OBSERVED`. |
| P2 | The first formal preflight found one unformatted test comprehension. | Ruff formatted the single file; the full verifier was rerun from the beginning and passed. |

## Final review result

- P0: `0`
- P1: `0`
- P2: `0`
- Migration: forward/additive; empty downgrade/re-upgrade passes and populated Gold history refuses
  downgrade.
- Isolation: no production table has a foreign key to any `gold_*` table; legacy Phase 3–8 readers
  are unchanged.
- Metrics: zero support is `NOT_OBSERVED`, never a pass; numerator/denominator/support and time
  cutoff violations remain visible.
- Human evidence: real Gold `0`; independent Annotator/Verifier/Adjudicator evidence
  `0 / NOT_OBSERVED`; Locked benchmark `NOT_RUN`.
- Secrets/provider: credential file was not read; external provider calls remain `NOT_RUN`.

Verdict: `GOLD_BENCHMARK_DIFF_REVIEW_PASS`, based on the fresh post-review verifier recorded in
`P9B_GOLD_BENCHMARK_TEST_SUMMARY.md`.
