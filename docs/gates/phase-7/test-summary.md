# Phase 7 Test Summary

Evidence date: 2026-08-22. Candidate:
`50f0794f5470a64691ea938936ac832bf5d67796`.

## Fresh local candidate

The isolated verifier completed with exit code `0`:

```powershell
$env:COMPOSE_PROJECT_NAME = "deepaha-phase7-engineering-candidate"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-phase7.ps1
```

Observed results:

- Ruff format: 209 files; Ruff lint: pass;
- mypy: 200 source files, no issues;
- default backend suite: 434 passed, 179 integration/live tests deselected;
- focused v0.1-v0.6 contract, feedback, review, validation, API and verifier-scope suite: 130 passed;
- focused Phase 7 PostgreSQL integration suite: 13 passed;
- Alembic: upgrade to `20260822_0007`, downgrade to `20260822_0006`, re-upgrade and drift check pass;
- Web: lint and typecheck pass; 20 test files / 47 tests pass; production build passes;
- exact `deepaha-phase7-engineering-candidate` containers, network and volumes removed in `finally`;
- verifier output: synthetic workflow only, real participants `0`, human track `NOT_STARTED`, Release
  Qualification `NOT_STARTED`, decision `HOLD_MISSING_HUMAN_EVIDENCE`.

The root verifier was then rerun independently and also exited `0` with backend 434, Web 47 and a
successful production build. A separate exact Phase 7 PostgreSQL run reconfirmed all 13 integration
cases and removed project `deepaha-phase7-targeted` plus its volumes.

## Coverage highlights

- contract export determinism and historical schema compatibility;
- immutable UPDATE/DELETE rejection and migration round trip;
- exact owner/ranking/match/opportunity/user-state/evidence binding;
- purpose revocation, role denial, unknown/other-owner equivalence and private cache headers;
- idempotency replay/conflict and whole-transaction rollback;
- confirmed adjudication before label curation;
- simulation/human evidence-class and metric-shape separation;
- one-direction uniqueness and synthetic-only mandatory hold;
- controlled user/reviewer Web states and production build.

## Browser evidence

Headed Chrome exercised submission, owner status, role denial, assessment, adjudication, label
creation, user-safe confirmed status, dependency failure/retry, desktop/mobile layout, keyboard,
focus and reduced motion. See [browser-verification.md](browser-verification.md).

## Remote evidence

Not recorded yet. Engineering Gate remains `OPEN` until the stacked draft PR's exact candidate has
all eight required GitHub Actions jobs successful.
