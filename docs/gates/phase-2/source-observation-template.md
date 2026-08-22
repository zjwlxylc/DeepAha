# Phase 2 source observation evidence template

Status: **TEMPLATE ONLY — NOT VALIDATED EVIDENCE**

This template defines the evidence shape for the Phase 2 live source window. Its
presence does not qualify the Phase 2 release. Release Qualification remains
`IN_PROGRESS` until a real run, fresh-copy verification, unified verification,
and final-candidate remote CI all succeed. This does not reopen or block the
Phase 2 Engineering Gate by itself.

## Safe execution

Run from the repository root with the observation file outside the repository:

```powershell
$env:DEEPAHA_ALLOW_LIVE_SOURCE_CHECK = "true"
powershell -ExecutionPolicy Bypass -File scripts/run-phase2-source-observation.ps1 `
  -Rounds 5 `
  -IntervalSeconds 21600 `
  -OutputPath "<external-path>\phase2-source-observation.json" `
  -RunDueRoundsOnly
```

Repeat the same command against the same output path only when `next_due_at` has
arrived. The runner checkpoints the external JSON through a temporary-file
replacement after each endpoint and skips checkpointed endpoint results on
resume. The database transaction and external JSON are not a cross-system atomic
commit, and the runner has no cross-process lock: use exactly one writer. If an
interruption occurs between collection commit and checkpoint, inspect database
observations/health and the JSON before resuming. The observation file does not
save response bodies, headers, cookies, credentials, or object-store content.

## Required acceptance evidence

- Registry digest and exact candidate commit SHA.
- Exactly 10 active, policy-approved official endpoints.
- Five completed rounds separated by at least the Registry minimum interval.
- Observation span of at least 24 hours from the first round start to the fifth
  round completion.
- At least 50 final endpoint results.
- Valid result ratio of at least 98% (`SUCCEEDED` or `NOT_MODIFIED`, with both a
  content SHA-256 and immutable object key).
- Per-result collection run ID, bounded attempt metadata, final outcome, HTTP
  status/error code, content digest, and object key.
- Source health evidence after every endpoint collection.
- Actual operator maintenance minutes and a description of every intervention.
- Confirmation that no login, CAPTCHA, paywall, robots restriction, or technical
  control was bypassed.

## Completion record

Populate only from the final external JSON and command output:

| Field | Actual value |
| --- | --- |
| Candidate commit | Pending |
| Registry SHA-256 | Pending |
| Started at (UTC) | Pending |
| Completed at (UTC) | Pending |
| Observation span | Pending |
| Completed rounds | Pending |
| Endpoint results | Pending |
| Valid results | Pending |
| Failed results | Pending |
| Valid ratio | Pending |
| Operator maintenance minutes | Pending |
| Observation file SHA-256 | Pending |

Do not replace pending values with targets or estimates. Failed or policy-invalid
results remain part of the record; they must not be removed to improve the ratio.
