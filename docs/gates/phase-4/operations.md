# Phase 4 Candidate Operations

## Evidence state

- Implemented: a disposable isolated verifier exists for the Phase 4 candidate.
- Locally verified: the isolated verifier passed and removed its exact disposable project.
- remote CI: pending.
- Synthetic evaluation: verifier runs offline fixed data and prints its scoped result.
- Blocked: these commands do not promote, merge, release or close a Gate.

## Current candidate verification

```powershell
$env:COMPOSE_PROJECT_NAME = "deepaha-phase4-candidate"
& ./scripts/verify-phase4.ps1
Remove-Item Env:COMPOSE_PROJECT_NAME
& ./scripts/verify.ps1
```

The Phase 4 verifier owns and removes only the exact project name passed to it and uses
`infra/compose.phase4.yaml`.

## Required update after upstream Gate closure

After receiving the exact Phase 3 closing SHA and verifying that it includes the authorized Phase
2 closing baseline:

```powershell
git fetch origin
git switch codex/phase-4-rules-eligibility-evaluation
git rebase --onto <exact-phase-3-closing-sha> 5a5847be266980e83eccd8718c23b77e788ee481
git diff <exact-phase-3-closing-sha>...HEAD -- backend/src/deepaha/contracts backend/migrations contracts
$env:COMPOSE_PROJECT_NAME = "deepaha-phase4-post-gates"
& ./scripts/verify-phase4.ps1
Remove-Item Env:COMPOSE_PROJECT_NAME
& ./scripts/verify.ps1
git push --force-with-lease origin codex/phase-4-rules-eligibility-evaluation
```

Then wait for all required remote CI jobs, update exact evidence URLs and perform a new promotion
decision. Do not reuse the current synthetic result as real annotated evidence.
