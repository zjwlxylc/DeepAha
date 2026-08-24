# P9-B0 Identity & Provenance Architecture Closure — Test Summary

Date: 2026-08-24 (Asia/Shanghai)

This file records observed engineering evidence for the exact pre-commit B0 candidate. It does not
start Release Qualification, create Gold, run the 100-source/14-day target or mark v0.8 `STABLE`.

## Dedicated B0 verifier

Command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-p9b-b0.ps1 `
  -ComposeProjectName deepaha-p9b-b0-final-12872
```

Observed result: exit `0`.

| Check | Observed result |
| --- | --- |
| Backend non-integration regression | `661 passed, 292 deselected in 22.16s` |
| Web Vitest | `24` files, `61` tests passed |
| Web production build | passed |
| B0 deterministic/contract/document tests | `90 passed` |
| B0 PostgreSQL integration tests | `29 passed` |
| Full PostgreSQL integration regression | `288 passed, 4 skipped, 661 deselected in 108.32s` |
| Alembic drift before downgrade | no new upgrade operations detected |
| Migration downgrade/re-upgrade | `20260824_0011 -> 20260822_0010 -> 20260824_0011`, passed |
| Alembic drift after re-upgrade | no new upgrade operations detected |
| Exact compose cleanup | containers, volumes and network removed |

The downgrade path succeeds only for an empty P9-B migration footprint. Populated P9-B history is
covered by an integration test that fails closed rather than deleting identity/provenance history.

## P9-A preservation verifier

Command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-source-acquisition-platform.ps1 `
  -ComposeProjectName deepaha-source-acquisition-p9b-b0-evidence-12872
```

Observed result: exit `0`.

| Check | Observed result |
| --- | --- |
| Root backend regression | `661 passed, 292 deselected` |
| Web Vitest/build | `61 passed`; production build passed |
| Historical Phase 2 PostgreSQL regression | `288 passed, 4 skipped, 661 deselected`; `232 passed` |
| Historical Phase 8 directed regression | `76 passed`; `47 passed`; Playwright `1 passed` |
| Source Acquisition offline tests | `139 passed` |
| Source Acquisition PostgreSQL/replay tests | `44 passed, 1 skipped` |
| Source Acquisition migration downgrade/re-upgrade/drift | passed; no new upgrade operations detected |
| Exact compose cleanup | Phase 2, Phase 8 and Source Acquisition containers, volumes and networks removed |

The verifier emitted the preserved P9-A axes exactly as:

```text
SOURCE ACQUISITION PLATFORM ENGINEERING GATE=CLOSED
Release Qualification=NOT_STARTED
100-source/14-day target=NOT_RUN
```

The existing reviewed P9-A status remains Independent Revalidation `PASS`, `P0=0 / P1=0 / P2=0`
and Contract `IMPLEMENTED`, not `STABLE`.

## Gate boundary

These checks can close the bounded P9-B0 Engineering Gate only. P9-A Release Qualification remains
`NOT_STARTED`, its 100-source/14-day target remains `NOT_RUN`, and P9-B Engineering Gate remains
`OPEN` until the later P9-B slices and final verifier are complete.
