# P9-B Gold Governance & Executable Benchmark — Test Summary

Date: 2026-08-24 (Asia/Shanghai)

All executed labels, identities, blocks and manifests were synthetic/controlled engineering
fixtures. They do not constitute real Gold, independent human evidence, benchmark qualification or
Release Qualification.

## Fresh post-review formal verifier

Command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-p9b-gold-benchmark.ps1 `
  -ComposeProjectName deepaha-p9b-gold-review-31417
```

Observed result: exit `0`.

| Check | Observed result |
| --- | --- |
| Backend non-integration regression | `701 passed, 306 deselected in 27.80s` |
| Web Vitest | `24` files, `61` tests passed |
| Web production build | passed |
| Gold contract/governance/import/benchmark/verifier tests | `29 passed` |
| Gold PostgreSQL/migration tests | `4 passed` |
| Full PostgreSQL integration regression | `302 passed, 4 skipped, 701 deselected` |
| Alembic drift before downgrade | no new upgrade operations detected |
| Empty migration downgrade/re-upgrade | `20260824_0014 -> 20260824_0013 -> 20260824_0014`, passed |
| Alembic drift after re-upgrade | no new upgrade operations detected |
| Exact Compose cleanup | containers, volumes and network removed |

## Evidence boundary

- Real Gold entries: `0 / NOT_OBSERVED`.
- Independent human role decisions: `0 / NOT_OBSERVED`.
- Calibration/Development/Validation/Locked manifests with real answers: `NOT_RUN`.
- Locked Acceptance benchmark: `NOT_RUN`.
- P9-B overall Engineering Gate: `OPEN` pending later Slices.
- P9-B Release Qualification: `NOT_STARTED`.
- P9-A Release Qualification: `NOT_STARTED`; 100-source/14-day: `NOT_RUN`.

Verifier status output:

```text
P9-B GOLD GOVERNANCE AND BENCHMARK SLICE ENGINEERING GATE=CLOSED
Real Gold entries=0 / NOT_OBSERVED
Independent human evidence=0 / NOT_OBSERVED
Locked Acceptance benchmark=NOT_RUN
Release Qualification=NOT_STARTED
```
