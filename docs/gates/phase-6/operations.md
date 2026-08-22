# Phase 6 Operations

Phase 6 has no production deployment or long-running service runbook. The supported operation in
this Gate package is the isolated engineering verifier:

```powershell
$env:COMPOSE_PROJECT_NAME = "deepaha-phase6-<unique-lowercase-suffix>"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-phase6.ps1
Remove-Item Env:COMPOSE_PROJECT_NAME
```

The verifier accepts only `deepaha-phase6-*`, checks exclusive ownership of PostgreSQL 55436 and
Moto 55004, runs root quality plus focused contract/profile/match/action/API/integration/migration
and Web checks, and removes only the exact project and disposable volumes in `finally`.

The browser seed refuses every database except `127.0.0.1:55436/deepaha`. It generates temporary
runtime credentials and prints one only for the operator's current disposable browser session; do
not save that output, a Cookie, storage state or screenshots. Browser/API/Web processes must be
stopped by their recorded process IDs, then the exact Phase 6 Compose project must be removed.

Do not point fixture auth, the seed or verifier at a real database. Do not connect to or reuse Phase
2–5 ports/projects. There is no production deploy, rollback, backup, monitoring, alerting, identity
or privacy-request procedure because Release Qualification is `NOT_STARTED`.
