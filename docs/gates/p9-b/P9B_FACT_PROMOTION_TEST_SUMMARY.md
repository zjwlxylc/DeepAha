# P9-B Fact Promotion & Dormant Unit Rules — Test Summary

Date: 2026-08-24 (Asia/Shanghai)

This evidence covers engineering behavior on synthetic/controlled fixtures. It does not represent
real Gold, independent human verification, production qualification accuracy or Release
Qualification.

## Formal verifier

Command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-p9b-fact-chain.ps1 `
  -ComposeProjectName deepaha-p9b-facts-final-24591
```

Observed result: exit `0`.

| Check | Observed result |
| --- | --- |
| Backend non-integration regression | `684 passed, 302 deselected in 22.49s` |
| Web Vitest | `24` files, `61` tests passed |
| Web production build | passed |
| Fact/Rule contract and verifier-scope tests | `22 passed` |
| Fact-chain PostgreSQL and migration tests | `5 passed` |
| Full PostgreSQL integration regression | `298 passed, 4 skipped, 684 deselected in 138.47s` |
| Alembic drift before downgrade | no new upgrade operations detected |
| Empty migration downgrade/re-upgrade | `20260824_0013 -> 20260824_0012 -> 20260824_0013`, passed |
| Alembic drift after re-upgrade | no new upgrade operations detected |
| Exact compose cleanup | containers, volumes and network removed |

## Engineering assertions exercised

- Exact Opportunity and Unit target bindings retain the real composite OpportunityVersion identity.
- Extraction blocks must belong to the frozen SourceBundleRevision and keep their field EvidenceRef.
- Candidate producer self-verification and response reuse fail closed in service and PostgreSQL.
- Known/UNKNOWN facts promote only from compatible immutable verification decisions.
- Fact content is immutable; FactSet supersession and dependency invalidation are audited.
- RuleCandidate Evidence is limited to its selected facts; Rule approval is independent.
- Unit RuleCandidates cannot compile to legacy Opportunity RuleSet; persisted UnitRuleSet is
  `DORMANT` and absent from Phase 4–8 production readers.
- Migration is forward/additive; empty downgrade succeeds and populated history refuses downgrade.

## Evidence boundary

- Real Gold entries: `0`.
- Independent Annotator/Verifier/Adjudicator decisions: `0 / NOT_OBSERVED`.
- Real provider calls: `NOT_RUN`.
- P9-B overall Engineering Gate: `OPEN` pending later slices.
- Release Qualification: `NOT_STARTED`.

Verifier status output:

```text
P9-B FACT PROMOTION SLICE ENGINEERING GATE=CLOSED
Independent human Gold evidence=NOT_OBSERVED
UnitRuleSet activation=DORMANT
Release Qualification=NOT_STARTED
```
