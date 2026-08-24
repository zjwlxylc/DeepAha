# P9-B DocumentBlock & Field Locator Slice — Code Review

Date: 2026-08-24 (Asia/Shanghai)

## Review boundary

This review covers migration `20260824_0012`, v0.8 DocumentBlock/locator contracts, explicit P9-B
HTML/PDF/XLSX/DOCX parsers, persistence/replay helpers and the Slice verifier. It does not approve
Gold labels, field facts, OCR, real DOCX/XLSX coverage or any later P9-B promotion/benchmark work.

The environment does not authorize a separate review agent. This is an explicit post-implementation
diff review, not independent human annotation, adjudication or accountable product approval.

## Findings resolved before commit

| Original severity | Finding | Resolution and regression evidence |
| --- | --- | --- |
| P1 | Replacing the existing parser version caused recorded P9-A replay to fail before object integrity checks. | Historical `0.2.0` parser classes remain unchanged; explicit `0.8.0` P9-B parser classes create new parse identities. P9-A replay regression passes. |
| P1 | A custom legacy-contract parser could emit blocks under the historical parse identity. | DocumentService now requires the exact P9-B parse contract whenever blocks are emitted and requires blocks for that contract; rollback is asserted. |
| P1 | First-parse EvidenceRef order differed from idempotent replay order. | Both return UUID-sorted EvidenceRef IDs; integration asserts equality. |
| P1 | The composite parent FK proved same-Document ownership but did not enforce parent-before-child order. | The insert trigger now requires an existing lower ordinal parent in the same Document; XLSX range/cell persistence exercises the relationship. |
| P2 | The first formal verifier run stopped on three formatter-only differences. | Ruff formatter was applied without behavior changes; the full verifier was rerun from the beginning. |

## Final review result

- P0: `0`
- P1: `0`
- P2: `0`
- Migration: forward/additive; empty downgrade succeeds; populated block history refuses downgrade.
- Legacy read/replay paths: no replacement or silent parser-version rewrite.
- OCR: `DISABLED`; no OCR block can enter the P9-B locator service.
- Real controlled DOCX/XLSX Gold coverage: `0 / NOT_OBSERVED`.
- Secret/content review: synthetic fixtures only; no provider secret or real response body added.

Verdict: `DOCUMENT_BLOCK_DIFF_REVIEW_PASS`, subject to the fresh final verifier result in
`P9B_DOCUMENT_BLOCK_TEST_SUMMARY.md` and a dedicated local commit.
