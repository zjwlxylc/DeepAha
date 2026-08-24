# P9-A Source Acquisition Platform Test Summary

Evidence date: 2026-08-24. Status: final independent revalidation `PASS`.

Audit base: `cedce6f229dc341bf20107200b61e1f197b0d3d7`

Candidate: `94741c19a3a8471866930a46f7e70d85b7e79a68`

Audit range: `cedce6f229dc341bf20107200b61e1f197b0d3d7..94741c19a3a8471866930a46f7e70d85b7e79a68`

Independent revalidation result: `PASS` (`P0=0 / P1=0 / P2=0`)

## Full isolated verifier

The following exact command completed with exit code `0`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-source-acquisition-platform.ps1 `
  -ComposeProjectName deepaha-source-acquisition-fix-verify-e752 `
  -ControlledCorpusRoot <approved-controlled-corpus-root>
```

Observed results:

- root quality: Ruff format `281` files, Ruff lint pass, mypy `269` source files pass;
- root backend: `627 passed, 274 deselected`;
- root Web: ESLint/typecheck pass, `24/24` test files and `61/61` tests pass, production build pass;
- Phase 2 isolated Gate: `270 passed, 4 skipped, 627 deselected`; additional focused suite
  `218 passed`; full migration to head and no schema drift;
- Phase 8 isolated Gate: backend `76 passed`, integration `47 passed`, migration
  downgrade/re-upgrade/drift pass, Web `24/24` and `61/61`, Chromium `1 passed`;
- P9-A offline unit/policy/replay/scope suite: `139 passed`;
- P9-A PostgreSQL/S3/migration/controlled-replay suite: `45 passed`;
- P9-A migrations: upgrade from empty, downgrade to `20260822_0008`, re-upgrade and
  `alembic check` all pass;
- exact P9-A containers, volumes and network were removed after the run.

The final verifier output was:

```text
SOURCE ACQUISITION PLATFORM ENGINEERING GATE=CLOSED
Release Qualification=NOT_STARTED
100-source/14-day target=NOT_RUN
```

## Separate controlled replay evidence

The real-corpus replay was also run directly with the controlled object root and returned
`1 passed`. It verified all 16 real entries; no network Fetcher is available to the replay runner.
The S02 Opportunity replay separately returned `1 passed`. It selected the real corpus entry by
`source_acquisition_entry_id`, installed socket/DNS denial during replay, created the actual
Evaluation/Document/Evidence path, and then resolved the Opportunity. The direct DocumentService
invalid-evaluation bypass regression is included in the `45 passed` integration suite. The
first-five integration-cost Gate separately returned `1 passed`.

Live qualification is not part of the verifier or default CI. It requires an explicit wrapper
switch, an exact Recipe and endpoint, a request cap, a minimum interval and a process-local opt-in.
