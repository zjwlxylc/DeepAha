# Phase 4 Acceptance Results

## Evidence state

- Implemented: exact candidate `94bab9e7397a8ccb43d95da3f68bfa1fc6df9a07` contains Tasks
  1–9.
- Locally verified: isolated Phase 4 verifier and root regression passed at
  `2026-08-21T22:41:13Z`.
- remote CI: [run 32534085134](https://github.com/zjwlxylc/DeepAha/actions/runs/32534085134)
  completed with all five jobs successful.
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

Delivery remains [draft PR #4](https://github.com/zjwlxylc/DeepAha/pull/4),
`OPEN/DRAFT/UNMERGED`, with the exact stacked base and head branches.
