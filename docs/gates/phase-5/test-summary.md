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

Exact candidate SHA `492c8b34562dca59c2a66d6e4d3ea769345803ca` completed GitHub Actions
[run 32549701629](https://github.com/zjwlxylc/DeepAha/actions/runs/32549701629) with overall
conclusion `success`:

- `backend-quality`: `success`;
- `web-quality`: `success`;
- `integration`: `success`;
- `phase3-resolution`: `success`;
- `phase4-eligibility`: `success`;
- `phase5-public-trust`: `success`.

This satisfies the remote evidence required to close the Engineering Gate. The subsequent
docs-only final head is separately required to pass the same six jobs and is recorded in draft PR
#5 after it completes.

Release Qualification remains `NOT_STARTED`; fixed fixtures and synthetic browser output do not
measure real Gold completeness, source freshness or official-link reproducibility at candidate
scale.
