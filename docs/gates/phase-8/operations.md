# Phase 8 Operations

Phase 8 has no production deployment or long-running provider runbook. The supported operation is
the isolated engineering verifier:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-phase8.ps1 `
  -ComposeProjectName deepaha-phase8-<unique-lowercase-suffix>
```

The verifier accepts only an exact `deepaha-phase8-*` project name. It checks PostgreSQL `55438`,
Moto `55006`, API `8008` and Web `3088` before use; runs the root verifier, migrations, focused and
integration tests, seeded fixture, Web checks and Chromium smoke; and removes only that exact
project's containers, network and disposable volumes in `finally`.

The seeder refuses every database except `127.0.0.1:55438/deepaha` and requires an empty fixture
scope. Never point fixture auth, the seeder, `TEST_INBOX` or this verifier at real users or a real
database. It must not reuse Phase 2–7 ports, projects or volumes.

Worker engineering behavior is bounded: one claim has a 60-second lease; expired claims are
recoverable; transient failures retry after 60 then 300 seconds and the third attempt becomes
terminal. Current user control suppresses without consuming an adapter attempt; invalid immutable
bindings fail for defect review instead of being repaired silently.

There is no approved production schedule, queue topology, provider monitoring, backup/restore,
privacy-request, rollback, incident-response or deployment procedure. Those omissions block
production use, not this isolated verifier.
