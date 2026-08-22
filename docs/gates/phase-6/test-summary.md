# Phase 6 Test Summary

Evidence date: 2026-08-22. Evidence type: local engineering verification with fixed synthetic data.

## Final local candidate

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-phase6.ps1` completed on code
commit `66aaaac94ae8062740452daed6f855ee2b56f083`:

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
React keys, stale action form state and API error-boundary refresh.

## Browser evidence

Headed Chromium completed the public-detail → fit-check → progressive profile → personal detail →
90-day priorities → save/status/material → audited official-link flow. A real local API interruption
showed the explicit failure state and recovered after API restoration. See
[browser-verification.md](browser-verification.md) for exact observations and evidence limits.

## Remote evidence

Not yet available. Engineering Gate closure requires the final stacked candidate's exact SHA and
all seven required GitHub Actions jobs. Synthetic CI remains engineering evidence and cannot
qualify real-user metrics.
