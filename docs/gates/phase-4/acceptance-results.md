# Phase 4 Acceptance Results

## Evidence state

- Implementation: `IMPLEMENTED` on merge commit
  `09526c61a1a0410e9a9127c989ecfaecf3f0ea02`.
- Engineering Gate: `OPEN` pending exact-SHA remote CI.
- Release Qualification: `NOT_STARTED`.
- Contract Maturity: `IMPLEMENTED` (not `STABLE`).
- Locally verified: isolated Phase 4 verifier and root regression passed at
  `2026-08-22T01:27:25Z`.
- remote CI: pending for the integrated candidate.
- Synthetic evaluation: 12 fixed Golden cases passed with zero unexpected negatives.

## Acceptance matrix

| Criterion | Candidate evidence | Result |
|---|---|---|
| v0.4 additive contract | 21-schema compatibility collection; v0.1–v0.4 renderer/import checks | Implemented |
| Immutable persistence | Additive PostgreSQL migration, restrictive references and replay rows | Implemented |
| Controlled DSL/compiler | Fixed fields/operators, graph/type validation and cycle rejection | Implemented |
| Eligibility protection | Four states; official deterministic evidence required for `INELIGIBLE` | Implemented |
| First deterministic rules | Major, education, graduation, date, region, certificate and missing facts | Implemented |
| Match replay | Exact component/input versions, canonical hash and explainable diff | Implemented |
| Golden fixtures | CC0 manifest, 20 mother and 100 versioned synthetic profiles | Implemented |
| Evaluation safety | Integer counts and protected unexpected-negative failure | Synthetic only |
| Real false-negative threshold | Governed real annotated dataset absent | Release Qualification not started |

The Engineering Gate may close only after the required exact-SHA remote jobs succeed. No row
authorizes release, Release Qualification, or contract promotion to `STABLE`.

Delivery remains [draft PR #4](https://github.com/zjwlxylc/DeepAha/pull/4),
`OPEN/DRAFT/UNMERGED`, with the exact stacked base and head branches.
