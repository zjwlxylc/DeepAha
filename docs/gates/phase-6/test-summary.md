# Phase 6 Test Summary

Evidence date: 2026-08-22. Evidence types: local engineering verification and remote exact-SHA CI
with fixed synthetic data.

## Final local candidate

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-phase6.ps1` completed on code
commit `d30fbac84e94a3b465ead09f17c1b8c220ab638d`:

- Ruff format: 169 files; Ruff lint: pass;
- mypy: 161 source files, no issues;
- default backend suite: 383 passed, 164 integration/live tests deselected;
- Web: lint and typecheck pass; 15 test files / 31 tests passed twice; production build passed twice;
- Phase 6 offline contract/profile/auth/action/API/scope suite: 35 passed;
- Phase 6 PostgreSQL profile/match/action/API/vertical-slice/isolation suite: 10 passed;
- Alembic: upgrade to `20260822_0006`, downgrade to `20260822_0005`, re-upgrade and drift check passed;
- exact `deepaha-phase6-*` containers, network and disposable volumes were removed in `finally`;
- verifier reported profiles=2, public opportunities=3, real users=0, real Gold=0, Release Qualification `NOT_STARTED`.

Targeted RED/GREEN evidence additionally covers removal of committed plaintext fixture credentials,
purpose-revocation read denial, backslash-based return redirect rejection, duplicate EvidenceRef
React keys, stale action form state, API error-boundary refresh and Phase 6-only browser-seed test
collection.

## Browser evidence

Headed Chromium completed the public-detail → fit-check → progressive profile → personal detail →
90-day priorities → save/status/material → audited official-link flow. A real local API interruption
showed the explicit failure state and recovered after API restoration. See
[browser-verification.md](browser-verification.md) for exact observations and evidence limits.

## Remote evidence

Initial candidate `9b859ac912dcb98438a82635f4d5a8685e172ff0` failed run `32558860910` in
`integration` and `phase3-resolution`: both generic jobs collected a browser-seed assertion that is
safe to execute only against the exact Phase 6 disposable database on port 55436. The dedicated
`phase6-profile-action` job succeeded. Commit `d30fbac` scopes that assertion to its exact database;
the full local verifier then passed again.

Corrected candidate `d30fbac84e94a3b465ead09f17c1b8c220ab638d` completed GitHub Actions run
`32559110870` with all seven jobs successful: `backend-quality`, `web-quality`, `integration`,
`phase3-resolution`, `phase4-eligibility`, `phase5-public-trust` and `phase6-profile-action`.
Synthetic CI remains engineering evidence and cannot qualify real-user metrics.
