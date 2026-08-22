# DeepAha Phase 7 Feedback, Review and Dual-track Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:executing-plans` task-by-task,
> `superpowers:test-driven-development` for every feature/fix, `superpowers:systematic-debugging`
> for failures, and `superpowers:verification-before-completion` before every completion claim.
> The user authorized continuous inline execution in this isolated worktree; do not dispatch
> subagents or pause for the usual execution-method choice.

**Goal:** Deliver an authenticated, owner-isolated and auditable Phase 7 path from immutable raw
feedback through human-role review, approved label, one improvement direction, offline/shadow
candidate records and a mandatory synthetic-only release hold, with simulation and real-human
evidence contracts kept strictly separate.

**Architecture:** Add v0.6 contracts and migration `0007`; implement separate `feedback`, `review`
and `validation` modules; expose personal and reviewer APIs; add a thin personal correction/status
flow and controlled reviewer UI; verify with fixed CC0 synthetic fixtures on Phase 7-only services.
No feedback path writes rules, match history, eligibility, ranking or production configuration.

**Tech stack:** Python 3.14, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL 18, pytest,
Next.js 16, React 19, TypeScript 5.9, Vitest/Testing Library, Playwright/Chromium, Docker Compose and
GitHub Actions.

**Approved spec:**
`docs/superpowers/specs/2026-08-22-phase-7-feedback-review-validation-design.md`

**Exact base:** `7f2cebc2afcfc6cb7061ed5bb91d79b824e91a3d`

**Branch:** `codex/phase-7-feedback-review-validation`

## Execution status (2026-08-22)

- Tasks 1–8: completed with independent commits and ordinary pushes.
- Task 9: completed; fresh local verification, full implementation review and Gate candidate
  evidence pass.
- Task 10: in progress; PR #8 is open/draft/unmerged and implementation candidate `63536985...`
  passed all eight jobs in run `32571667136`. The docs-only closure and its final exact-SHA CI remain.
  Release Qualification is `NOT_STARTED`; v0.6 is `IMPLEMENTED`, not `STABLE`.

## Global constraints

- Keep Phase 6 PR #6 open/draft/unmerged and do not modify its branch or worktree.
- Never rebase, force-push, merge, ready, release or mark a contract `STABLE`.
- Never connect to, start, stop, remove or occupy ports `55432`–`55436` or `55000`–`55004`.
- Phase 7 may use only `deepaha-phase7-*`, PostgreSQL `55437` and Moto `55005`.
- Preserve every v0.1–v0.5 Schema byte and existing Python import path.
- Use fixed, license-safe fixtures marked synthetic, no personal data, no business truth and not
  Release Qualification eligible.
- Do not accept an authoritative client `user_id`, arbitrary evidence URL, upload or unbounded JSON.
- Do not let LLM/model output adjudicate feedback or hard qualification.
- Do not implement notification, Outbox, reminder, push, mini-program or calendar behavior.
- Use `apply_patch` for source/document edits, exact-path `git add`, independent commits and ordinary
  push after each task. Never use `git add .` or `git add -A`.
- For each task: establish RED, inspect the intended failure, implement the minimum, run focused
  GREEN and risk regression, inspect/stage exact diff, commit and push.

---

## Task 1: Define additive v0.6 feedback governance contracts

**Files:**

- Create: `backend/src/deepaha/contracts/phase7.py`
- Modify: `backend/src/deepaha/contracts/__init__.py`
- Modify: `backend/src/deepaha/contracts/export.py`
- Create: `backend/tests/contracts/test_phase7_contracts.py`
- Create: `contracts/schemas/v0.6.0/feedback-event.schema.json`
- Create: `contracts/schemas/v0.6.0/feedback-evidence-link.schema.json`
- Create: `contracts/schemas/v0.6.0/feedback-review-case-snapshot.schema.json`
- Create: `contracts/schemas/v0.6.0/feedback-confidence-assessment.schema.json`
- Create: `contracts/schemas/v0.6.0/feedback-adjudication.schema.json`
- Create: `contracts/schemas/v0.6.0/approved-feedback-label.schema.json`
- Create: `contracts/schemas/v0.6.0/improvement-candidate.schema.json`
- Create: `contracts/schemas/v0.6.0/offline-evaluation-candidate.schema.json`
- Create: `contracts/schemas/v0.6.0/shadow-test-candidate.schema.json`
- Create: `contracts/schemas/v0.6.0/validation-run.schema.json`
- Create: `contracts/schemas/v0.6.0/release-gate-decision.schema.json`
- Create: `contracts/examples/v0.6.0/phase-7-example.json`

**Interfaces:** strict frozen Pydantic models and enums named in the approved design; a discriminated
simulation/human validation run contract; `render_phase7_schemas()` exporting `v0.6.0`.

- [ ] **Step 1: Write RED contract tests**

Assert exact enum/value bounds, immutable/frozen models, owner IDs absent from input commands,
500-character statement bound, one-direction candidate shape, ordered offline→shadow→Gate IDs and:

```python
def test_synthetic_evidence_cannot_construct_human_validation() -> None:
    with pytest.raises(ValidationError):
        HumanValidationRunSchemaV06.model_validate(
            human_run_values(synthetic=True, evidence_class="SYNTHETIC_FEEDBACK_WORKFLOW_ONLY")
        )

def test_release_acceptance_requires_both_qualified_tracks() -> None:
    with pytest.raises(ValidationError):
        ReleaseGateDecisionSchemaV06.model_validate(
            release_values(decision="CANDIDATE_ACCEPTED_FOR_FUTURE_IMPLEMENTATION", human_run_id=None)
        )
```

Read committed bytes for v0.1–v0.5 and assert every renderer remains identical.

- [ ] **Step 2: Run RED**

```powershell
Push-Location backend
uv run pytest tests/contracts/test_phase7_contracts.py -q
Pop-Location
```

Expected: collection fails because `deepaha.contracts.phase7` is absent.

- [ ] **Step 3: Implement minimum contracts and deterministic export**

Use distinct models for raw feedback, evidence, queue snapshot, assessment, adjudication, label,
improvement, offline, shadow and Gate. Do not place review state on FeedbackEvent. Use separate
simulation and human metric models; do not use a generic free-form metrics dictionary.

- [ ] **Step 4: Export v0.6 schemas and strict synthetic example**

```powershell
Push-Location backend
$env:PYTHONPATH = "src"
uv run python -m deepaha.contracts.export .. --version 0.6.0
Remove-Item Env:PYTHONPATH
Pop-Location
```

The example must end in `HOLD_MISSING_HUMAN_EVIDENCE`, select only
`EXPLANATION_CLARITY`, declare `SYNTHETIC_FEEDBACK_WORKFLOW_ONLY`, and contain no real-person data.

- [ ] **Step 5: Verify GREEN and historical compatibility**

```powershell
Push-Location backend
uv run pytest tests/contracts/test_phase1_contracts.py tests/contracts/test_phase2_contracts.py `
  tests/contracts/test_phase3_contracts.py tests/contracts/test_phase4_contracts.py `
  tests/contracts/test_phase6_contracts.py tests/contracts/test_phase7_contracts.py -q
uv run ruff format --check src/deepaha/contracts tests/contracts/test_phase7_contracts.py
uv run ruff check src/deepaha/contracts tests/contracts/test_phase7_contracts.py
uv run mypy src/deepaha/contracts tests/contracts/test_phase7_contracts.py
Pop-Location
git diff --check
```

- [ ] **Step 6: Exact commit and push**

Stage only the listed Task 1 files, inspect `git diff --cached --check`, commit
`feat: define phase 7 feedback contracts`, and ordinary-push.

---

## Task 2: Add immutable persistence and separate reviewer identity

**Files:**

- Create: `backend/src/deepaha/feedback/__init__.py`
- Create: `backend/src/deepaha/feedback/models.py`
- Create: `backend/src/deepaha/review/__init__.py`
- Create: `backend/src/deepaha/review/models.py`
- Create: `backend/src/deepaha/review/auth.py`
- Create: `backend/src/deepaha/validation/__init__.py`
- Create: `backend/src/deepaha/validation/models.py`
- Modify: `backend/src/deepaha/core/settings.py`
- Modify: `backend/src/deepaha/db/models.py`
- Create: `backend/migrations/versions/20260822_0007_phase7_feedback_review_validation.py`
- Create: `backend/tests/feedback/__init__.py`
- Create: `backend/tests/review/__init__.py`
- Create: `backend/tests/validation/__init__.py`
- Create: `backend/tests/review/test_auth.py`
- Create: `backend/tests/integration/test_phase7_persistence.py`
- Modify: `backend/tests/integration/test_migrations.py`
- Create: `infra/compose.phase7.yaml`

- [ ] **Step 1: Create isolated compose definition**

Use PostgreSQL `18.4-alpine3.23` at `127.0.0.1:55437` and Moto `5.2.2` at
`127.0.0.1:55005`, disposable credentials and PostgreSQL tmpfs. Do not start it before verifying
both ports are free.

- [ ] **Step 2: Write RED auth, migration and persistence tests**

Cover reviewer fixture mode disabled outside development/test, digest-only credentials, role and
purpose derivation, expiry/revocation, all tables/FKs/checks, exact stream versions, and PostgreSQL
rejection of `UPDATE`/`DELETE` for immutable Phase 7 facts. Assert no old row is rewritten and a
populated `0007` downgrade refuses before data loss.

Start only the exact Task 2 project after confirming its two ports are free:

```powershell
$phase7Project = "deepaha-phase7-task2-$PID"
if (Get-NetTCPConnection -State Listen -LocalPort 55437,55005 -ErrorAction SilentlyContinue) {
    throw "Phase 7 ports are occupied"
}
docker compose --project-name $phase7Project --file infra/compose.phase7.yaml up -d --wait
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_phase7_local_only@127.0.0.1:55437/deepaha"
$env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55005"
```

Run RED in that database; expected failures are missing modules/tables/revision. Keep only this
exact project for the remaining Task 2 checks, then remove it and its disposable volumes in a
`finally` block and clear the Phase 7 environment variables.

- [ ] **Step 3: Implement minimum models, auth and migration**

Create separate reviewer account/session tables, user/reviewer Phase 7 idempotency tables,
feedback/evidence, review snapshot/assessment/adjudication/label and validation candidate/run/Gate
tables. Add Phase 7-specific immutable-mutation trigger functions. Add a supporting Phase 6 unique
constraint only if the exact owner/match composite FK requires it.

- [ ] **Step 4: Verify migration and auth GREEN**

```powershell
Push-Location backend
uv run pytest tests/review/test_auth.py -q
uv run alembic upgrade head
uv run pytest -m integration tests/integration/test_phase7_persistence.py `
  tests/integration/test_migrations.py --strict-markers
uv run alembic downgrade 20260822_0006
uv run alembic upgrade head
uv run alembic check
uv run ruff format --check src/deepaha/feedback src/deepaha/review src/deepaha/validation `
  migrations/versions/20260822_0007_phase7_feedback_review_validation.py
uv run ruff check src/deepaha/feedback src/deepaha/review src/deepaha/validation `
  migrations/versions/20260822_0007_phase7_feedback_review_validation.py
uv run mypy src/deepaha/feedback src/deepaha/review src/deepaha/validation
Pop-Location
```

- [ ] **Step 5: Exact commit and push**

Commit `feat: persist phase 7 feedback governance` from exact Task 2 paths only.

---

## Task 3: Submit owner-bound immutable feedback

**Files:**

- Create: `backend/src/deepaha/feedback/schemas.py`
- Create: `backend/src/deepaha/feedback/service.py`
- Create: `backend/src/deepaha/api/feedback.py`
- Modify: `backend/src/deepaha/main.py`
- Create: `backend/tests/feedback/test_service.py`
- Create: `backend/tests/api/test_feedback.py`
- Create: `backend/tests/integration/test_phase7_feedback_submission.py`
- Create: `backend/tests/integration/test_phase7_feedback_isolation.py`

- [ ] **Step 1: Write service/API RED tests**

Test atomic event+initial evidence+queue creation, exact version binding, required current purpose,
exact consent, idempotent replay, changed-body `409`, evidence allowlist and status projection.
Assert unknown and other-owner IDs return byte-identical `404` bodies and no `user_id`, reviewer,
confidence, token or SQL detail leaks.

Snapshot RuleSet/MatchSnapshot/EligibilityResult/ranking rows before submission and prove every row
and digest is unchanged afterward.

- [ ] **Step 2: Run RED and inspect missing-service failures**

```powershell
Push-Location backend
uv run pytest tests/feedback/test_service.py tests/api/test_feedback.py -q
Pop-Location
```

- [ ] **Step 3: Implement FeedbackService and personal API**

Implement `submit`, `append_evidence`, `list_owned` and `get_owned`. Canonicalize commands, hash with
owner/operation, require one `Idempotency-Key`, use server-derived principal and transact all facts
atomically. Register only the approved `/api/v1/me` feedback routes.

- [ ] **Step 4: Verify focused and integration GREEN**

```powershell
Push-Location backend
uv run pytest tests/feedback tests/api/test_feedback.py tests/api/test_personal.py -q
uv run pytest -m integration tests/integration/test_phase7_feedback_submission.py `
  tests/integration/test_phase7_feedback_isolation.py `
  tests/integration/test_phase6_user_isolation.py --strict-markers
uv run ruff format --check src/deepaha/feedback src/deepaha/api/feedback.py tests/feedback `
  tests/api/test_feedback.py
uv run ruff check src/deepaha/feedback src/deepaha/api/feedback.py tests/feedback `
  tests/api/test_feedback.py
uv run mypy src/deepaha/feedback src/deepaha/api/feedback.py tests/feedback `
  tests/api/test_feedback.py
Pop-Location
```

- [ ] **Step 5: Exact commit and push**

Commit `feat: submit immutable personal feedback`.

---

## Task 4: Review, adjudicate and curate labels

**Files:**

- Create: `backend/src/deepaha/review/schemas.py`
- Create: `backend/src/deepaha/review/service.py`
- Create: `backend/src/deepaha/api/review.py`
- Modify: `backend/src/deepaha/main.py`
- Create: `backend/tests/review/test_service.py`
- Create: `backend/tests/api/test_review.py`
- Create: `backend/tests/integration/test_phase7_review_workflow.py`
- Create: `backend/tests/integration/test_phase7_reviewer_authorization.py`

- [ ] **Step 1: Write RED workflow and authorization tests**

Cover finite queue ordering, due/overdue projection, minimum case view, role-by-operation denial,
user/reviewer credential separation, assessment append, transition legality, confirmed evidence
requirement, rejected reason requirement, label preconditions and reviewer idempotency.

Assert user status contains public state/rationale only; reviewer identity, internal risk and
confidence remain absent.

- [ ] **Step 2: Run RED**

```powershell
Push-Location backend
uv run pytest tests/review/test_service.py tests/api/test_review.py -q
Pop-Location
```

- [ ] **Step 3: Implement ReviewService and reviewer API**

Queue state changes append a new snapshot. Assessment, adjudication and label are separate writes.
Use the current authenticated reviewer role/purpose; never accept reviewer IDs in commands. No
endpoint edits rules, matches, opportunities or user profiles.

- [ ] **Step 4: Verify focused and PostgreSQL GREEN**

```powershell
Push-Location backend
uv run pytest tests/review tests/api/test_review.py tests/api/test_feedback.py -q
uv run pytest -m integration tests/integration/test_phase7_review_workflow.py `
  tests/integration/test_phase7_reviewer_authorization.py `
  tests/integration/test_phase7_feedback_isolation.py --strict-markers
uv run ruff format --check src/deepaha/review src/deepaha/api/review.py tests/review `
  tests/api/test_review.py
uv run ruff check src/deepaha/review src/deepaha/api/review.py tests/review `
  tests/api/test_review.py
uv run mypy src/deepaha/review src/deepaha/api/review.py tests/review `
  tests/api/test_review.py
Pop-Location
```

- [ ] **Step 5: Exact commit and push**

Commit `feat: adjudicate governed feedback`.

---

## Task 5: Gate one dual-track improvement candidate

**Files:**

- Create: `backend/src/deepaha/validation/schemas.py`
- Create: `backend/src/deepaha/validation/service.py`
- Create: `backend/tests/validation/test_service.py`
- Create: `backend/tests/integration/test_phase7_validation_gate.py`

- [ ] **Step 1: Write RED validation tests**

Test one selected candidate per cycle, one component/change digest, label prerequisite, offline
before shadow, shadow before Gate, separate dataset IDs/metric models/evidence labels, and rejection
of synthetic inputs by the human track.

The fixed end-to-end assertion is:

```python
decision = service.decide(cycle_id)
assert decision.decision is ReleaseDecision.HOLD_MISSING_HUMAN_EVIDENCE
assert decision.simulation_run_id is not None
assert decision.human_run_id is None
assert unchanged_online_decision_digests() == before
```

- [ ] **Step 2: Run RED**

```powershell
Push-Location backend
uv run pytest tests/validation/test_service.py -q
Pop-Location
```

- [ ] **Step 3: Implement deterministic ValidationService**

Expose internal methods `select_improvement`, `record_offline`, `record_shadow`,
`record_simulation_run`, `record_human_run` and `decide`. Permit no dynamic code, arbitrary metric
dictionary, network call or online update. A human run requires non-synthetic consented provenance.

- [ ] **Step 4: Verify GREEN and Phase 4 evaluation regression**

```powershell
Push-Location backend
uv run pytest tests/validation tests/evaluation -q
uv run pytest -m integration tests/integration/test_phase7_validation_gate.py `
  tests/integration/test_phase4_evaluation_run.py --strict-markers
uv run ruff format --check src/deepaha/validation tests/validation `
  tests/integration/test_phase7_validation_gate.py
uv run ruff check src/deepaha/validation tests/validation `
  tests/integration/test_phase7_validation_gate.py
uv run mypy src/deepaha/validation tests/validation `
  tests/integration/test_phase7_validation_gate.py
Pop-Location
```

- [ ] **Step 5: Exact commit and push**

Commit `feat: gate one feedback improvement candidate`.

---

## Task 6: Add the minimal personal and reviewer Web flows

**Files:**

- Create: `web/lib/feedback.ts`
- Create: `web/lib/review-feedback.ts`
- Create: `web/app/feedback-actions.ts`
- Create: `web/app/review-actions.ts`
- Create: `web/components/feedback-form.tsx`
- Create: `web/components/feedback-status.tsx`
- Create: `web/components/review-case-panel.tsx`
- Modify: `web/app/me/opportunities/[publicId]/page.tsx`
- Create: `web/app/me/opportunities/[publicId]/feedback/page.tsx`
- Create: `web/app/me/opportunities/[publicId]/feedback/loading.tsx`
- Create: `web/app/me/opportunities/[publicId]/feedback/error.tsx`
- Create: `web/app/me/feedback/page.tsx`
- Create: `web/app/me/feedback/loading.tsx`
- Create: `web/app/me/feedback/error.tsx`
- Create: `web/app/me/feedback/[feedbackId]/page.tsx`
- Create: `web/app/me/feedback/[feedbackId]/loading.tsx`
- Create: `web/app/me/feedback/[feedbackId]/error.tsx`
- Create: `web/app/review/feedback/page.tsx`
- Create: `web/app/review/feedback/loading.tsx`
- Create: `web/app/review/feedback/error.tsx`
- Create: `web/app/review/feedback/[caseId]/page.tsx`
- Create: `web/app/review/feedback/[caseId]/loading.tsx`
- Create: `web/app/review/feedback/[caseId]/error.tsx`
- Modify: `web/app/globals.css`
- Create: `web/tests/feedback-form.test.tsx`
- Create: `web/tests/feedback-status.test.tsx`
- Create: `web/tests/review-feedback.test.tsx`
- Create: `web/tests/feedback-actions.test.ts`
- Create: `web/tests/review-actions.test.ts`
- Modify: relevant Phase 6 detail/state tests only where the new link is asserted.

- [ ] **Step 1: Write RED Web tests**

Assert controlled fields/evidence checkboxes/consent, sensitive-data warning, status language,
reviewer queue/case forms, Server Action calls, separate reviewer cookie, no token in rendered
output, role error states, `role=alert`, keyboard-native controls and no admin dashboard features.

- [ ] **Step 2: Run RED**

```powershell
Push-Location web
corepack pnpm test -- feedback review personal-detail
Pop-Location
```

- [ ] **Step 3: Implement server-only clients, actions and pages**

Reuse Phase 5/6 tokens and layout. Personal calls use `deepaha_phase6_session`; reviewer calls use
`deepaha_phase7_reviewer_session`. Initial loads use Server Components; mutations use Server
Actions and safe route-local revalidation. Do not add reviewer navigation to the public header.

- [ ] **Step 4: Verify Web GREEN and build**

```powershell
Push-Location web
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
corepack pnpm build
Pop-Location
git diff --check
```

- [ ] **Step 5: Exact commit and push**

Commit `feat: add controlled feedback review web`.

---

## Task 7: Add fixed fixtures and the complete synthetic vertical slice

**Files:**

- Create: `backend/tests/fixtures/feedback/phase7-feedback.json`
- Create: `backend/tests/fixtures/feedback/phase7-feedback.manifest.json`
- Create: `backend/tests/feedback/support.py`
- Create: `backend/tests/feedback/seed_phase7_browser.py`
- Create: `backend/tests/feedback/test_phase7_fixture.py`
- Create: `backend/tests/integration/test_phase7_vertical_slice.py`
- Create: `backend/tests/integration/test_phase7_transaction_rollback.py`

- [ ] **Step 1: Write RED fixture and end-to-end tests**

Assert manifest bytes, CC0/synthetic/privacy flags, stable IDs, no plaintext credentials and exact
host/port guard. The vertical slice must run:

```text
existing match -> submit correction -> append official EvidenceRef -> assess -> confirm
-> create synthetic-provenance label -> select EXPLANATION_CLARITY
-> offline candidate -> shadow candidate -> HOLD_MISSING_HUMAN_EVIDENCE
```

Assert every online RuleSet/match/eligibility/ranking digest and row count is unchanged.

- [ ] **Step 2: Run RED, implement fixture/loader/seeder, then GREEN**

The seeder accepts only `127.0.0.1:55437/deepaha`, requires an empty Phase 7 fixture scope,
generates temporary credentials at runtime, prints synthetic boundaries and never prints reviewer
or user credential digests.

```powershell
Push-Location backend
uv run pytest tests/feedback/test_phase7_fixture.py -q
uv run pytest -m integration tests/integration/test_phase7_vertical_slice.py `
  tests/integration/test_phase7_transaction_rollback.py --strict-markers
Pop-Location
```

- [ ] **Step 3: Verify deterministic bytes**

Run the generator/loader twice, compare SHA-256 for every declared fixture file and require no
difference. Tamper with a copied byte and assert validation fails before parsing.

- [ ] **Step 4: Exact commit and push**

Commit `test: cover phase 7 synthetic workflow`.

---

## Task 8: Add isolated verifier, CI and real-browser engineering evidence

**Files:**

- Create: `scripts/verify-phase7.ps1`
- Create: `backend/tests/test_phase7_verifier_scope.py`
- Modify: `.github/workflows/ci.yml`
- Create: `docs/gates/phase-7/browser-verification.md`

- [ ] **Step 1: Write verifier-scope RED tests**

Require exact `deepaha-phase7-*`, compose file, 55437/55005, exact-project cleanup and all inherited
jobs plus `phase7-feedback-review`. Forbid every Phase 2–6 port/project, live source, external model
and participant command.

- [ ] **Step 2: Implement verifier and CI job**

The local verifier runs root quality, v0.1–v0.6 compatibility, Phase 7 offline/API/auth tests,
PostgreSQL integration, migration round trip/drift, fixtures and Web build. It prints:

```text
SYNTHETIC_FEEDBACK_WORKFLOW_ONLY
real participants=0
human track=NOT_STARTED
Release Qualification=NOT_STARTED
release decision=HOLD_MISSING_HUMAN_EVIDENCE
```

- [ ] **Step 3: Run the complete verifier**

```powershell
$env:COMPOSE_PROJECT_NAME = "deepaha-phase7-engineering-candidate"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-phase7.ps1
Remove-Item Env:COMPOSE_PROJECT_NAME
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
```

- [ ] **Step 4: Perform Playwright browser QA**

Read the Playwright skill and `ui-ux-pro-max/references/pro-rules.md`. Start only the Phase 7
project and recorded API/Web processes. At 1440x900 and 375x812 plus keyboard-only flow, verify:

1. personal detail -> correction form;
2. exact EvidenceRef selection and explicit consent;
3. submission and owner-safe status;
4. reviewer queue with separate reviewer session;
5. assessment -> adjudication -> label;
6. user-visible confirmed state without reviewer/confidence disclosure;
7. controlled auth/dependency failure and recovery;
8. no horizontal overflow, hidden focus, token, percentage, Phase 8 or deployment control.

Store screenshots outside the repository, inspect them, then remove temporary browser state and
stop only recorded processes/project. Record observations, not screenshots, in the Gate document.

- [ ] **Step 5: Exact commit and push**

Commit `ci: verify phase 7 feedback review`.

---

## Task 9: Complete Gate evidence and full implementation review

**Files:**

- Create: `docs/gates/phase-7/README.md`
- Create: `docs/gates/phase-7/acceptance-results.md`
- Create: `docs/gates/phase-7/test-summary.md`
- Create: `docs/gates/phase-7/code-review.md`
- Create: `docs/gates/phase-7/security-and-compliance.md`
- Create: `docs/gates/phase-7/dual-track-validation.md`
- Create: `docs/gates/phase-7/operations.md`
- Create: `docs/gates/phase-7/deferred-decisions.md`
- Modify: `docs/development/README.md`
- Modify: `docs/development/system-roadmap.md`
- Modify: `docs/development/architecture.md`
- Modify: `docs/development/quality-and-release.md`
- Create: `docs/development/domain-contracts-v0.6.md`
- Modify: Phase 7 spec/plan only for truthful implementation evidence/check boxes.

- [x] **Step 1: Run fresh verification-before-completion**

Rerun Phase 7 and root verifiers from fresh output. Record exact commands, timestamps, counts,
migration result and synthetic/human boundary. Do not reuse earlier output.

- [x] **Step 2: Review the full diff**

Inspect `7f2cebc2...HEAD` for every path and line. Run diff/whitespace, tracked artifact, secret,
credential, database/cache/build/browser artifact, license, old-Schema-byte, migration mutation,
port/project isolation, `user_id`, authorization, privacy, evidence provenance, LLM, online-rule
mutation, notification/Outbox and claim-language scans. Inspect every hit in context.

Any Critical/Important defect returns to RED and a separate minimal fix commit before Gate docs.

- [x] **Step 3: Write truthful Gate candidate evidence**

Before exact-SHA remote CI:

- Implementation `IMPLEMENTED` only if code/tests actually exist and pass;
- Engineering Gate `OPEN`;
- Release Qualification `NOT_STARTED`;
- v0.6 `IMPLEMENTED`, not `STABLE`;
- synthetic feedback/reviewer flow and real participants `0` stated prominently;
- single direction `EXPLANATION_CLARITY` described only as fixture input;
- Gate decision `HOLD_MISSING_HUMAN_EVIDENCE`.

- [x] **Step 4: Exact commit and push**

Commit `docs: record phase 7 engineering evidence`.

---

## Task 10: Create stacked draft PR and close only the Engineering Gate

**Files:** update Phase 7 Gate/design evidence only after exact candidate CI success.

- [x] **Step 1: Verify branch and upstream boundary**

Fetch origin; prove clean local/remote equality and exact Phase 6 ancestry. Re-fetch PR #6 and
confirm open/draft/unmerged, exact head `7f2cebc2...`, and no unexpected base movement.

- [x] **Step 2: Create stacked draft PR**

Use the authenticated GitHub connector:

- title: `Phase 7: feedback, review and dual-track validation`;
- base: `codex/phase-6-profile-match-personal-action`;
- head: `codex/phase-7-feedback-review-validation`;
- draft: `true`.

The body records exact base/head, four axes, local commands/counts, browser evidence, synthetic vs
human boundary, one candidate direction, mandatory hold and explicit Phase 8/release exclusions.

- [x] **Step 3: Wait for exact implementation candidate CI**

Required jobs:

- `backend-quality`;
- `web-quality`;
- `integration`;
- `phase3-resolution`;
- `phase4-eligibility`;
- `phase5-public-trust`;
- `phase6-profile-action`;
- `phase7-feedback-review`.

If any fails, use `superpowers:systematic-debugging`, reproduce the first causal failure, add a RED
test when applicable, make the minimum fix, rerun risk-matched local verification, commit/push and
restart exact-SHA qualification.

- [ ] **Step 4: Close Engineering Gate and push docs-only closure**

After exact implementation SHA success, update evidence with its SHA/run/job conclusions and set:

- Implementation `IMPLEMENTED`;
- Engineering Gate `CLOSED`;
- Release Qualification `NOT_STARTED`;
- v0.6 `IMPLEMENTED`, not `STABLE`.

Commit `docs: close phase 7 engineering gate`, push, then wait again because the final handoff SHA
must itself pass all eight jobs. Put final non-recursive exact-SHA run evidence in the PR body.

- [ ] **Step 5: Finish the branch without integration**

Invoke `superpowers:finishing-a-development-branch`. The user has already selected the keep/push
stacked-draft path. Do not merge, ready, rebase, delete branch or remove the worktree. Verify final
cleanliness, local/remote equality, ancestry, open/draft/unmerged PR and every final job success.

## Plan self-review record

- **Approved-design coverage:** Tasks 1–7 cover every contract and runtime object in the approved
  chain; Tasks 8–10 cover browser, verifier, CI, Gate and delivery.
- **Boundary coverage:** No task implements Phase 8, production identity, arbitrary evidence
  ingestion, online learning, rule mutation, merge, release or `STABLE`.
- **Evidence coverage:** Simulation, synthetic feedback and consented-human tracks have distinct
  contracts/labels; no task fabricates real participant evidence.
- **Safety coverage:** Exact owner/version/EvidenceRef bindings, reviewer roles, existence privacy,
  immutable rows, restrictive downgrade and unchanged online-decision assertions are executable.
- **Single-variable coverage:** One database-enforced selected improvement per cycle; fixture uses
  only `EXPLANATION_CLARITY` and must end in a hold.
- **Execution selection:** Continuous inline execution is already authorized and multi-agent
  dispatch is prohibited; use `superpowers:executing-plans` in this worktree.
