# Phase 5 Test Summary

Evidence date: 2026-08-22. Evidence type: locally verified engineering evidence.

## Final local candidate

`powershell -ExecutionPolicy Bypass -File scripts/verify-phase5.ps1` ran with compose project
`deepaha-phase5-final-candidate` and completed successfully:

- Ruff format: 142 files formatted;
- Ruff lint: pass;
- mypy: 135 source files, no issues;
- default backend suite: 348 passed, 152 deselected;
- Web: lint pass, typecheck pass, 8 test files / 11 tests passed, production build pass;
- Phase 5 offline contract/projection/API/scope suite: 166 passed;
- Phase 5 PostgreSQL integration/read-only suite: 29 passed;
- Alembic: upgrade to `20260822_0005`, downgrade to `20260822_0004`, re-upgrade and `alembic check` all passed;
- verifier evidence: `SYNTHETIC_FIXTURE_ONLY`, 3 governed records, real Gold records 0;
- exact compose project and volumes removed in `finally`.

An independent fresh `scripts/verify.ps1` rerun then reproduced the 348 backend and 11 Web test
results and production build. `git diff --check` passed.

## Coverage map

- persistence constraints, exact version FK, non-destructive populated downgrade refusal;
- v0.1-v0.4 contract compatibility and schema byte stability;
- official-source and minimum precedence evidence boundary;
- public field completeness, deterministic search/filter/sort/cursor pagination;
- GET-only routing, read-only transaction, safe 400/404/503 responses;
- public DTO negative assertions for storage, profile, rule, eligibility and model fields;
- Web populated/loading/empty/error/detail/Phase 6 boundary states;
- keyboard focus, mobile target size, responsive overflow and browser console checks.

## Remote evidence

Remote CI is not yet recorded. Engineering Gate is therefore `OPEN`. After the stacked draft PR
has an exact-SHA successful run, this file will be updated with run ID and every required job
conclusion.

Release Qualification remains `NOT_STARTED`; fixed fixtures and synthetic browser output do not
measure real Gold completeness, source freshness or official-link reproducibility at candidate
scale.
