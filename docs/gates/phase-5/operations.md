# Phase 5 Operations

Phase 5 has no production deployment or long-running service runbook. The only supported operation
in this Gate package is an isolated engineering verifier.

```powershell
$env:COMPOSE_PROJECT_NAME = "deepaha-phase5-<unique-lowercase-suffix>"
powershell -ExecutionPolicy Bypass -File scripts/verify-phase5.ps1
Remove-Item Env:COMPOSE_PROJECT_NAME
```

The verifier accepts only a `deepaha-phase5-*` project, checks exclusive ownership of PostgreSQL
55435 and Moto 55003, runs root quality plus focused Phase 5 contract/API/integration/migration
checks, and removes only that exact compose project and its disposable volumes in `finally`.

Browser QA additionally uses temporary application ports selected for the current run, a guarded
seed helper that refuses any database other than `127.0.0.1:55435/deepaha`, and exactly three
synthetic rows. Application processes must be terminated by their recorded process/session IDs;
screenshots and Playwright state remain outside the repository.

Do not point the verifier or seed helper at a real database. Do not replace the fixture with scraped
or unlicensed originals. No Phase 2 observation, Phase 3 resolution or Phase 4 evaluation command
is part of Phase 5 verification.

There is no release, rollback, backup, live-data migration or production cache procedure because
Release Qualification is `NOT_STARTED` and production is out of scope.
