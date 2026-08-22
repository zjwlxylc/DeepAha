# Phase 8 Test Summary

Evidence date: 2026-08-23. Implementation candidate:
`6586f4b784afb05b0a5070d07a379dc663372e92`.

## Fresh local candidate

The exact isolated verifier completed with exit code `0` from
`2026-08-23T01:07:58.5747458+08:00` through
`2026-08-23T01:09:42.3433568+08:00`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-phase8.ps1 `
  -ComposeProjectName deepaha-phase8-final-6586f4b
```

Observed results:

- Ruff format: 242 files; Ruff lint: pass;
- mypy: 232 source files, no issues;
- default backend suite: 509 passed, 224 integration/live tests deselected;
- Phase 8 contract/notification/API/scope suite: 75 passed;
- Phase 8 PostgreSQL integration suite: 43 passed;
- Alembic: upgrade to `20260822_0008`, downgrade to `20260822_0007`, re-upgrade and drift check pass;
- Web: lint/typecheck pass, 24 test files / 59 tests pass twice, production build passes twice;
- Playwright Chromium: 1 seeded owner journey passes;
- exact containers, network and disposable volumes were removed; ports `55438`, `55006`, `8008`
  and `3088` had zero remaining listeners.

The fixed fixture manifest SHA-256 is
`abd81653e1c3f0f38594d88be55dc6558511dd4d3ab5e68f461899ff223f7815` and declares
`synthetic=true`, no personal/business truth, human participants `0` and Release Qualification
ineligible.

## Review and defect evidence

RED/GREEN review tests closed preference stream concurrency, immutable/composite Outbox bindings,
adapter failure budgeting, linked-opportunity concurrency and missing real-browser coverage. A
final P1 reproduced stale event-time preference/action/purpose bindings in three branches; the
worker now replays the exact event-time audience SQL and rejects each stale binding before adapter
invocation. Independent final review reports no unresolved P0/P1/P2.

## Remote implementation evidence

GitHub Actions run
[`32586782360`](https://github.com/zjwlxylc/DeepAha/actions/runs/32586782360) completed on exact
implementation SHA `6586f4b784afb05b0a5070d07a379dc663372e92`. All nine jobs succeeded:
`backend-quality`, `web-quality`, `integration`, `phase3-resolution`, `phase4-eligibility`,
`phase5-public-trust`, `phase6-profile-action`, `phase7-feedback-review` and
`phase8-deadline-reminder`.

This is engineering evidence only. The exact Gate-package commit still requires its own nine-job
success before Engineering Gate closure.
