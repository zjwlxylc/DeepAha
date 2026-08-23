# P9-A Source Acquisition Platform Test Summary

Evidence date: 2026-08-24. Code candidate: `76a0bf8`.

## Full isolated verifier

The following exact command completed with exit code `0`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-source-acquisition-platform.ps1 `
  -ComposeProjectName deepaha-source-acquisition-final `
  -ControlledCorpusRoot <approved-controlled-corpus-root>
```

Observed results:

- root quality: Ruff format `281` files, Ruff lint pass, mypy `269` source files pass;
- root backend: `627 passed, 273 deselected`;
- root Web: ESLint/typecheck pass, `24/24` test files and `61/61` tests pass, production build pass;
- Phase 2 isolated Gate: `270 passed, 3 skipped, 627 deselected`; additional focused suite
  `218 passed`; full migration to head and no schema drift;
- Phase 8 isolated Gate: backend `76 passed`, integration `47 passed`, migration
  downgrade/re-upgrade/drift pass, Web `24/24` and `61/61`, Chromium `1 passed`;
- P9-A offline unit/policy/replay/scope suite: `139 passed`;
- P9-A PostgreSQL/S3/migration/controlled-replay suite: `44 passed`;
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
The S02 Opportunity replay separately returned `1 passed`, and the first-five integration-cost Gate
separately returned `1 passed`.

Live qualification is not part of the verifier or default CI. It requires an explicit wrapper
switch, an exact Recipe and endpoint, a request cap, a minimum interval and a process-local opt-in.
