# Phase 4 Engineering Verification Operations

## Evidence state

- Implementation: `IMPLEMENTED`; a disposable isolated verifier exists for Phase 4.
- Engineering Gate: `CLOSED`.
- Release Qualification: `NOT_STARTED`.
- Contract Maturity: `IMPLEMENTED` (not `STABLE`).
- Locally verified: the isolated verifier passed and removed its exact disposable project.
- remote CI: exact candidate `1160c96f446f92a5cdce97b4aef11a7200262f0b` passed all five
  required jobs in [run 32543551989](https://github.com/zjwlxylc/DeepAha/actions/runs/32543551989).
- Synthetic evaluation: verifier runs offline fixed data and prints its scoped result.

## Current integrated verification

```powershell
$env:COMPOSE_PROJECT_NAME = "deepaha-phase4-engineering-gate"
& ./scripts/verify-phase4.ps1
Remove-Item Env:COMPOSE_PROJECT_NAME
& ./scripts/verify.ps1
```

The Phase 4 verifier owns and removes only the exact project name passed to it and uses
`infra/compose.phase4.yaml`.

## Closing-baseline record

Phase 2 closing commit `6c8a8fb63c68cfbb0f4cf54b6032bfb49a0ef65c` is an ancestor of Phase 3
closing commit `8003a1c2ab2485a1173b2d4bb9deafbbab6e949c`. Phase 4 integrated the latter
with merge commit `09526c61a1a0410e9a9127c989ecfaecf3f0ea02`, preserving both histories.

If a later authorized closing commit supersedes this baseline, use another explicit merge commit;
do not rebase or force-push the Phase 4 branch:

```powershell
git fetch origin
git switch codex/phase-4-rules-eligibility-evaluation
git merge --no-ff --no-commit <new-exact-phase-3-closing-sha>
git diff <new-exact-phase-3-closing-sha>...HEAD -- backend/src/deepaha/contracts backend/migrations contracts
$env:COMPOSE_PROJECT_NAME = "deepaha-phase4-updated-baseline"
& ./scripts/verify-phase4.ps1
Remove-Item Env:COMPOSE_PROJECT_NAME
& ./scripts/verify.ps1
git push origin codex/phase-4-rules-eligibility-evaluation
```

Resolve and commit only after schema/import, migration, identifier, evidence-semantics and replay
compatibility review succeeds. Then wait for all required remote CI jobs and update exact evidence.
These commands do not start Release Qualification, promote Contract Maturity to `STABLE`, merge
the draft PR or release the system. Do not reuse synthetic evaluation as real annotated evidence.
