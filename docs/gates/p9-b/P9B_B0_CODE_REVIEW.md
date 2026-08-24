# P9-B0 Identity & Provenance Architecture Closure — Code Review

Date: 2026-08-24 (Asia/Shanghai)

## Review boundary

This review covers the uncommitted B0 candidate based on planning commit
`a5ca543c961c2077df5688d29e888021fe655821`. It covers only identity, provenance,
DocumentParseIdentity, partition foundations, canonical hashes, additive migration, B0 contracts,
tests and the B0 verifier. It does not review or approve later P9-B slices.

The environment does not authorize a separate review agent for this task. The implementer therefore
performed an explicit second-pass diff review after implementation and before commit. This is an
engineering diff review, not independent human annotation, Gold adjudication or accountable product
approval.

## Findings resolved before Gate

| Original severity | Finding | Resolution and regression evidence |
| --- | --- | --- |
| P1 | Invalid explicit reversal validation could retire source Units before rejecting a non-matching split. | All reversal prerequisites are now checked before any Unit or UnitVersion mutation; an integration regression asserts no partial retirement. |
| P1 | Duplicate or already-active split child keys could be detected after the source Singleton was ended. | Split seeds are normalized, deduplicated and collision-checked before closing the Singleton; integration regressions assert atomic failure. |
| P1 | Mutable manifest invalidation audit fields were included in the frozen manifest hash. | The frozen projection now excludes successor/invalidation audit state; a regression proves invalidation leaves the frozen hash unchanged. |
| P1 | Repository idempotency could return an already-invalidated manifest when asked to persist the same frozen hash. | Persistence now rejects the non-`FROZEN` state; a regression covers the invalidated same-hash case. |
| P2 | Architecture text used a stale Singleton key and omitted the member provenance hash domain. | The closure now matches the implementation: `__default_singleton__` and all four frozen domains. |

## Final review result

- P0: `0`
- P1: `0`
- P2: `0`
- Legacy Stage 1 read paths: no P9-B UnitRuleSet or Gold read dependency introduced.
- Migration: forward/additive; historical migrations unchanged.
- Secret/content review: no live provider secret, response body or external Gold label is present.
- Human independence: no synthetic fixture or Codex decision is represented as independent Gold.

Verdict: `B0_DIFF_REVIEW_PASS`, subject to the test evidence recorded in
`P9B_B0_TEST_SUMMARY.md` and the dedicated local B0 commit.
