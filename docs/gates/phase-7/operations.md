# Phase 7 Operations

Phase 7 has no production deployment or long-running operations runbook. The supported operation is
the isolated engineering verifier:

```powershell
$env:COMPOSE_PROJECT_NAME = "deepaha-phase7-<unique-lowercase-suffix>"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-phase7.ps1
Remove-Item Env:COMPOSE_PROJECT_NAME
```

The verifier accepts only `deepaha-phase7-*`, checks that PostgreSQL `55437` and Moto `55005` are
free or owned by that exact project, runs root and Phase 7 checks, and removes only the exact
containers, network and disposable volumes in `finally`. It must not connect to or reuse Phase 2-6
ports/projects.

The browser seeder refuses every database except exact `127.0.0.1:55437/deepaha`, generates runtime
personal/reviewer credentials and must run with `PYTHONPATH=src` from `backend`. Do not save its
credentials, cookies, storage state, HTML or screenshots. Stop API/Web processes by their recorded
process IDs and remove only the exact Phase 7 compose project.

Do not point fixture auth, the seeder or verifier at real users or a real database. There is no
production deploy, rollback, monitoring, backup, restoration, privacy-request or incident-response
procedure because Release Qualification is `NOT_STARTED`.
