# Phase 4 Acceptance Results

## Evidence state

- Implemented: Tasks 1–8 are present at `fe96cabda9f34187b02604a725d8da7c57b30cd3`.
- Locally verified: isolated Phase 4 verifier and root regression passed.
- remote CI: pending.
- Synthetic evaluation: 12 fixed Golden cases passed with zero unexpected negatives.
- Blocked: acceptance cannot close Phase 4 while upstream Gates remain blocked.

## Acceptance matrix

| Criterion | Candidate evidence | Result |
|---|---|---|
| v0.4 additive contract | 21-schema compatibility collection; v0.1–v0.3 byte checks | Implemented |
| Immutable persistence | Additive PostgreSQL migration, restrictive references and replay rows | Implemented |
| Controlled DSL/compiler | Fixed fields/operators, graph/type validation and cycle rejection | Implemented |
| Eligibility protection | Four states; official deterministic evidence required for `INELIGIBLE` | Implemented |
| First deterministic rules | Major, education, graduation, date, region, certificate and missing facts | Implemented |
| Match replay | Exact component/input versions, canonical hash and explainable diff | Implemented |
| Golden fixtures | CC0 manifest, 20 mother and 100 versioned synthetic profiles | Implemented |
| Evaluation safety | Integer counts and protected unexpected-negative failure | Synthetic only |
| Real false-negative threshold | Governed real annotated dataset absent | Deferred / blocked |

No row authorizes release, Gate closure or contract promotion.
