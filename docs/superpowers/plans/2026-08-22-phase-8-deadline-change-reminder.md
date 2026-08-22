# DeepAha Phase 8 Deadline Change Reminder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended when the user explicitly authorizes subagents) or `superpowers:executing-plans` to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Also use
> `superpowers:test-driven-development` for each feature, `superpowers:systematic-debugging` for
> failures, and `superpowers:verification-before-completion` before each completion claim.

**Goal:** Build one user-controlled, exact-version deadline-change reminder path from a committed
`DEADLINE_CHANGED` OpportunityEvent through a transactional Outbox to an authenticated PostgreSQL
test inbox, without bypassing Phase 5 public governance or claiming human behavior evidence.

**Architecture:** Add an additive v0.7 contract and migration `0008`. Extend the existing Phase 3
Opportunity transaction with per-user reminder candidates, hold them until the exact `to_version`
is governed, then use a leased bounded worker and idempotent database adapter to deliver to a test
inbox. Reuse Phase 6 server-derived identity and personal-route privacy controls; add no queue
service or external provider.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL 18,
pytest, Next.js 16, React 19, TypeScript 5.9, Vitest/Testing Library, Playwright/Chromium,
Docker Compose, PowerShell and GitHub Actions.

**Spec:**
`docs/superpowers/specs/2026-08-22-phase-8-deadline-change-reminder-design.md`

**Exact base:** `c7ae6ac1192e010b13a5b83c2e09347978839e7b`

**Branch:** `codex/phase-8-deadline-change-reminders`

## Global Constraints

- Read the approved spec and `AGENTS.md` before Task 1 and again before Gate closeout.
- Preserve every committed byte under `contracts/schemas/v0.1.0` through `v0.6.0` and every
  existing Python import path.
- The only eligible event has type `DEADLINE_CHANGED`, exactly one changed field
  `application_window.closes_on`, two present unequal ISO dates and no identity merge/split.
- Candidate users must be saved and independently opted in at event commit time; saving alone is
  never notification consent and later opt-in is never retroactive. Their latest UserStateSnapshot
  must also permit the existing `ACTION_TRACKING` purpose.
- Exact `to_version` Phase 5 public governance is mandatory before any inbox insert.
- The only cadence is `AS_SOON_AS_GOVERNED`; the only target is `TEST_INBOX`.
- Do not add Redis, Celery, an external provider, push, email, SMS, mini-program, calendar, digest,
  quiet hours, frequency selection, multi-channel routing, admin UI or catalog approval API.
- Use fixed, permission-safe synthetic fixtures only. Never call a synthetic inbox read an open or
  report open, complaint, retention, trust, conversion or action metrics.
- Keep Phase 6/7 human Release Qualification at zero participants and
  `HOLD_MISSING_HUMAN_EVIDENCE`; it remains independent of the Phase 8 Engineering Gate.
- v0.7 starts `PROPOSED`, may reach at most `IMPLEMENTED` on engineering evidence, and must not be
  marked `STABLE` while Release Qualification is not `QUALIFIED`.
- Use only isolated Phase 8 services named `deepaha-phase8-*`, PostgreSQL host port `55438` and Moto
  host port `55006`. Never start, stop or inspect a Phase 2-7 Compose project or runtime.
- Use `apply_patch` for repository edits. Stage only exact Task files, never `git add .` or
  `git add -A`; inspect each staged diff, commit independently and ordinary-push.
- Do not create or change a PR, merge, mark ready, rebase, force-push, release or deploy unless a
  later user instruction explicitly authorizes that additional action.
- For every implementation task: establish RED, inspect the intended failure, implement the
  minimum, run focused GREEN and risk regression, then commit and ordinary-push.

---

## File Map

### Contract and persistence boundary

- `backend/src/deepaha/contracts/phase8.py`: frozen v0.7 enums and cross-boundary schemas only.
- `backend/src/deepaha/contracts/export.py`: deterministic v0.7 renderer/export selection.
- `backend/src/deepaha/notifications/models.py`: Phase 8 SQLAlchemy persistence models only.
- `backend/migrations/versions/20260822_0008_phase8_deadline_reminders.py`: additive schema,
  constraints, indexes and non-empty downgrade refusal.

### Application boundary

- `backend/src/deepaha/notifications/preferences.py`: owner-scoped append-only preference service.
- `backend/src/deepaha/notifications/candidates.py`: exact event recognizer and transaction-local
  candidate fan-out; never commits and never delivers.
- `backend/src/deepaha/notifications/worker.py`: governance promotion, lease claim, recheck, bounded
  retry, suppression and run summary.
- `backend/src/deepaha/notifications/adapters.py`: one PostgreSQL test-inbox adapter and explicit
  transient/permanent adapter outcomes.
- `backend/src/deepaha/notifications/inbox.py`: owner-scoped read projection only.
- `backend/src/deepaha/notifications/cli.py`: bounded local worker command; no HTTP trigger.
- `backend/src/deepaha/api/reminders.py`: personal preference and inbox routes.

### Verification and UI boundary

- `backend/tests/notifications/`: focused contracts for preferences, recognition, worker, adapter
  and inbox behavior.
- `backend/tests/integration/test_phase8_*.py`: PostgreSQL atomicity, governance and full-slice
  evidence.
- `backend/tests/fixtures/reminders/`: fixed synthetic source data and manifest.
- `web/lib/reminders.ts`: typed personal API client.
- `web/app/reminder-actions.ts`: one preference mutation server action.
- `web/components/reminder-preference-toggle.tsx`: labelled independent opt-in control.
- `web/components/reminder-inbox-card.tsx`: exact old/new deadline and evidence presentation.
- `web/app/me/reminders/`: test-inbox route states.
- `scripts/verify-phase8.ps1`, `infra/compose.phase8.yaml` and the
  `phase8-deadline-reminder` CI job: isolated final verifier.

---

### Task 1: Define the additive v0.7 reminder contract

**Files:**

- Create: `backend/src/deepaha/contracts/phase8.py`
- Modify: `backend/src/deepaha/contracts/__init__.py`
- Modify: `backend/src/deepaha/contracts/export.py`
- Create: `backend/tests/contracts/test_phase8_contracts.py`
- Create: `contracts/schemas/v0.7.0/reminder-preference-snapshot.schema.json`
- Create: `contracts/schemas/v0.7.0/deadline-change-reminder-intent.schema.json`
- Create: `contracts/schemas/v0.7.0/notification-delivery-attempt.schema.json`
- Create: `contracts/schemas/v0.7.0/test-inbox-entry.schema.json`
- Create: `contracts/examples/v0.7.0/phase-8-example.json`

**Interfaces:**

- Produces enums `ReminderKind`, `DeadlineChangeDirection`, `ReminderCadence`, `ReminderTarget`,
  `NotificationOutboxStatus` and `NotificationDeliveryOutcome`.
- Produces frozen models `ReminderPreferenceSnapshotSchemaV07`,
  `DeadlineChangeReminderIntentSchemaV07`, `NotificationDeliveryAttemptSchemaV07` and
  `TestInboxEntrySchemaV07`.
- Produces `render_phase8_schemas() -> dict[str, bytes]` and
  `write_phase8_schemas(repository_root: Path) -> dict[str, Path]`.

Enum values are closed: reminder kind `DEADLINE_CHANGED`; directions `ADVANCED|EXTENDED`; cadence
`AS_SOON_AS_GOVERNED`; target `TEST_INBOX`; Outbox states
`WAITING_GOVERNANCE|AVAILABLE|LEASED|DELIVERED|SUPPRESSED|FAILED`; delivery outcomes
`SUCCEEDED|TRANSIENT_FAILURE|PERMANENT_FAILURE`.

- [ ] **Step 1: Write RED enum, invariant and compatibility tests**

Add exact tests including:

```python
def test_first_slice_rejects_unsupported_target() -> None:
    with pytest.raises(ValidationError):
        ReminderPreferenceSnapshotSchemaV07.model_validate(
            {**preference_values(), "target": "WECHAT_MINI_PROGRAM"}
        )


def test_intent_requires_one_non_null_deadline_change() -> None:
    with pytest.raises(ValidationError):
        DeadlineChangeReminderIntentSchemaV07.model_validate(
            {**intent_values(), "old_closes_on": None}
        )


def test_v01_through_v06_renderers_remain_byte_identical() -> None:
    for version, renderer in HISTORICAL_RENDERERS.items():
        assert renderer() == committed_schema_bytes(version)
```

Also assert `ADVANCED` means `new_closes_on < old_closes_on`, `EXTENDED` means the inverse, all
UUID identifiers are UUIDv7 where existing contracts require it, evidence IDs are distinct fields,
cadence/target are fixed, attempts are positive and an inbox entry cannot contain open/read fields.

- [ ] **Step 2: Run RED and inspect the missing-module failure**

```powershell
Push-Location backend
uv run pytest tests/contracts/test_phase8_contracts.py -q
Pop-Location
```

Expected: collection fails because `deepaha.contracts.phase8` does not exist.

- [ ] **Step 3: Implement the minimum frozen contract models**

Define `Phase8ContractModel(ContractModel)` with `extra="forbid"` and `frozen=True`; use it with
`StrEnum`, not free-form dictionaries. The intent must contain these exact trace fields:

```python
class DeadlineChangeReminderIntentSchemaV07(ContractModel):
    reminder_id: EntityId
    user_id: EntityId
    opportunity_id: EntityId
    event_id: EntityId
    from_version: VersionNumber
    to_version: VersionNumber
    old_closes_on: date
    new_closes_on: date
    direction: DeadlineChangeDirection
    previous_evidence_ref_id: EntityId
    current_evidence_ref_id: EntityId
    action_snapshot_id: EntityId
    preference_snapshot_id: EntityId
    user_state_snapshot_id: EntityId
    consent_version: str
    detected_at: Instant
    created_at: Instant
    reminder_kind: Literal[ReminderKind.DEADLINE_CHANGED]
    cadence: Literal[ReminderCadence.AS_SOON_AS_GOVERNED]
    target: Literal[ReminderTarget.TEST_INBOX]
    contract_version: Literal["0.7.0"]
```

Add a model validator proving consecutive versions and direction/date agreement. Keep delivery
state out of the immutable intent model.

- [ ] **Step 4: Add deterministic export and strict synthetic example**

Extend the CLI choices with `0.7.0` and export only the four Phase 8 schemas into v0.7.0. The
example must say `SYNTHETIC_REMINDER_DELIVERY_ONLY`, target `TEST_INBOX`, contain one advanced and
one extended shape at most, and contain no real-person data or human metric.

```powershell
Push-Location backend
$env:PYTHONPATH = "src"
uv run python -m deepaha.contracts.export .. --version 0.7.0
Remove-Item Env:PYTHONPATH
Pop-Location
```

- [ ] **Step 5: Run GREEN, format/type checks and compatibility regression**

```powershell
Push-Location backend
uv run pytest tests/contracts -q
uv run ruff format --check src/deepaha/contracts tests/contracts/test_phase8_contracts.py
uv run ruff check src/deepaha/contracts tests/contracts/test_phase8_contracts.py
uv run mypy src/deepaha/contracts tests/contracts/test_phase8_contracts.py
Pop-Location
git diff --check
```

- [ ] **Step 6: Exact commit and ordinary push**

Stage only the Task 1 files, inspect `git diff --cached --check` and the generated schema diff,
commit `feat: define phase 8 reminder contracts`, then ordinary-push.

---

### Task 2: Add Phase 8 persistence and isolated runtime definition

**Files:**

- Create: `backend/src/deepaha/notifications/__init__.py`
- Create: `backend/src/deepaha/notifications/models.py`
- Modify: `backend/src/deepaha/db/models.py`
- Modify: `backend/src/deepaha/core/settings.py`
- Create: `backend/migrations/versions/20260822_0008_phase8_deadline_reminders.py`
- Modify: `backend/tests/integration/test_migrations.py`
- Create: `backend/tests/integration/test_phase8_persistence.py`
- Create: `infra/compose.phase8.yaml`

**Interfaces:**

- Produces models `ReminderPreferenceSnapshotModel`, `ReminderPreferenceIdempotencyRecordModel`,
  `NotificationOutboxModel`, `NotificationDeliveryAttemptModel` and `TestInboxEntryModel`.
- Produces settings `notification_worker_batch_size=50` and `notification_lease_seconds=60`, plus
  a non-user-configurable worker constant `RETRY_DELAYS_SECONDS = (60, 300)`.

- [ ] **Step 1: Create the isolated Compose definition without starting it**

Use `postgres:18.4-alpine3.23` on `127.0.0.1:55438`, `motoserver/moto:5.2.2` on
`127.0.0.1:55006`, disposable Phase 8 credentials and PostgreSQL tmpfs. The file may mirror the
structure of `infra/compose.phase7.yaml` but its names, credentials and ports must be Phase 8-only.

- [ ] **Step 2: Write RED model and migration tests**

Assert exact check constraints, foreign keys and uniqueness, including:

```python
def test_logical_delivery_key_is_unique(postgres_session: Session) -> None:
    postgres_session.add_all([outbox_row(), outbox_row()])
    with pytest.raises(IntegrityError):
        postgres_session.flush()


def test_phase8_nonempty_downgrade_refuses(alembic_database: Engine) -> None:
    seed_one_preference_and_outbox(alembic_database)
    with pytest.raises(CommandError, match="Phase 8 data exists"):
        downgrade_to("20260822_0007")
```

Also cover append-only preference/attempt/inbox rows, valid state/attempt transitions, non-negative
attempt counts, lease field coherence, sanitized error-code bounds, owner foreign keys, exact
OpportunityVersion binding, event/opportunity/to-version consistency and the indexes listed below.

Use these named index purposes and column orders:

```text
reminder_preference_snapshots (user_id, reminder_kind, version DESC)
personal_action_snapshots (opportunity_id, user_id, version DESC)
user_state_snapshots (user_id, version DESC)
notification_outbox (status, created_at, reminder_id)
notification_outbox (status, next_attempt_at, reminder_id)
notification_outbox (status, lease_until, reminder_id)
test_inbox_entries (user_id, delivered_at DESC, inbox_entry_id DESC)
```

- [ ] **Step 3: Confirm Phase 8 ports are free, start only the exact Task project and run RED**

```powershell
$phase8Project = "deepaha-phase8-task2-$PID"
if (Get-NetTCPConnection -State Listen -LocalPort 55438,55006 -ErrorAction SilentlyContinue) {
    throw "Phase 8 ports are occupied"
}
docker compose --project-name $phase8Project --file infra/compose.phase8.yaml up -d --wait
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_phase8_local_only@127.0.0.1:55438/deepaha"
Push-Location backend
uv run pytest -m integration tests/integration/test_phase8_persistence.py `
  tests/integration/test_migrations.py --strict-markers
Pop-Location
```

Expected: failure because revision `0008` and the notification models do not exist. Use a
PowerShell `try/finally` to remove only `$phase8Project --volumes --remove-orphans` and clear the
Phase 8 environment variable.

- [ ] **Step 4: Implement minimum models and additive migration**

Use the logical delivery uniqueness key exactly:

```python
UniqueConstraint(
    "user_id", "event_id", "to_version", "reminder_kind", "target",
    name="uq_notification_outbox_logical_delivery",
)
```

Add a composite candidate-to-event foreign key by adding a named unique constraint on
`opportunity_events(event_id, opportunity_id, to_version)` in `0008`; do not rewrite event rows.
Use immutable-mutation guard triggers for preference snapshots, attempts and inbox entries, matching
the repository's existing PostgreSQL trigger style. The Outbox row alone is mutable for the finite
operational state machine. Downgrade first checks all five Phase 8 tables and refuses while any row
exists.

- [ ] **Step 5: Run migration GREEN and safety regression**

With a fresh exact Phase 8 project, run:

```powershell
Push-Location backend
uv run alembic upgrade head
uv run pytest -m integration tests/integration/test_phase8_persistence.py `
  tests/integration/test_migrations.py --strict-markers
uv run alembic downgrade 20260822_0007
uv run alembic upgrade head
uv run alembic check
uv run ruff format --check src/deepaha/notifications tests/integration/test_phase8_persistence.py
uv run ruff check src/deepaha/notifications tests/integration/test_phase8_persistence.py
uv run mypy src/deepaha/notifications tests/integration/test_phase8_persistence.py
Pop-Location
```

The downgrade sequence uses an empty freshly migrated database; the non-empty refusal is a separate
transactional test. Clean up only the exact Phase 8 project in `finally`.

- [ ] **Step 6: Exact commit and ordinary push**

Stage only Task 2 files, inspect the migration in both directions, commit
`feat: add phase 8 reminder persistence`, and ordinary-push.

---

### Task 3: Implement independent reminder preferences and personal API

**Files:**

- Create: `backend/src/deepaha/notifications/preferences.py`
- Create: `backend/src/deepaha/notifications/schemas.py`
- Create: `backend/src/deepaha/api/reminders.py`
- Modify: `backend/src/deepaha/main.py`
- Create: `backend/tests/notifications/__init__.py`
- Create: `backend/tests/notifications/test_preferences.py`
- Create: `backend/tests/api/test_reminders.py`
- Create: `backend/tests/integration/test_phase8_preference_api.py`

**Interfaces:**

- `ReminderPreferenceService.get_current(principal: Principal) -> ReminderPreferenceSnapshotSchemaV07 | None`.
- `ReminderPreferenceService.set_enabled(principal: Principal, enabled: bool, *, idempotency_key: str) -> ReminderPreferenceSnapshotSchemaV07`.
- `ReminderPreferenceWrite(enabled: bool)` is the only accepted request body.
- Routes are exactly `GET/PUT /api/v1/me/reminder-preferences/deadline-change`.

- [ ] **Step 1: Write RED service tests**

Cover absent preference as disabled without inserting a row, append-only versioning, no-op writes,
idempotent replay, key/body conflict, owner isolation and server-derived user IDs. The no-op write
must still bind the idempotency key to the existing snapshot and must not create a new version.

```python
def test_saving_an_opportunity_does_not_enable_reminders(service, principal) -> None:
    save_opportunity(principal)
    assert service.get_current(principal) is None


def test_later_enable_has_no_retroactive_side_effect(service, principal) -> None:
    result = service.set_enabled(principal, True, idempotency_key="enable-once")
    assert result.enabled is True
    assert count_outbox_rows(principal.user_id) == 0
```

- [ ] **Step 2: Write RED API security tests**

Assert one Authorization header, required one Idempotency-Key on PUT, no accepted `user_id`, 401
fail-closed behavior, `private, no-store`, identical foreign/unknown behavior and 409 for key/body
conflict. Confirm GET returns JSON `null` with status 200 when no preference snapshot exists and a
snapshot after the first PUT; every non-null response reports `AS_SOON_AS_GOVERNED` and
`TEST_INBOX`.

- [ ] **Step 3: Run focused RED**

```powershell
Push-Location backend
uv run pytest tests/notifications/test_preferences.py tests/api/test_reminders.py -q
Pop-Location
```

Expected: missing preference service and reminder router failures.

- [ ] **Step 4: Implement the minimum preference service and router**

Reuse `Principal`, `require_principal`, `require_idempotency_key`, `PersonalApiProblem` and
`PRIVATE_CACHE_CONTROL`; do not copy authentication parsing. Canonical request hashing includes
user ID, operation `DEADLINE_REMINDER_PREFERENCE` and `{enabled}`. Use an injected UUIDv7 factory
and aware clock. Register only the reminder router in `main.py`.

- [ ] **Step 5: Run GREEN and PostgreSQL API regression**

```powershell
Push-Location backend
uv run pytest tests/notifications/test_preferences.py tests/api/test_reminders.py `
  tests/api/test_personal.py -q
uv run pytest -m integration tests/integration/test_phase8_preference_api.py --strict-markers
uv run ruff format --check src/deepaha/notifications src/deepaha/api/reminders.py
uv run ruff check src/deepaha/notifications src/deepaha/api/reminders.py
uv run mypy src/deepaha/notifications src/deepaha/api/reminders.py
Pop-Location
git diff --check
```

- [ ] **Step 6: Exact commit and ordinary push**

Stage only Task 3 files, commit `feat: add deadline reminder preferences`, and ordinary-push.

---

### Task 4: Capture exact deadline-change candidates in the Opportunity transaction

**Files:**

- Create: `backend/src/deepaha/notifications/candidates.py`
- Modify: `backend/src/deepaha/opportunities/service.py`
- Create: `backend/tests/notifications/test_candidates.py`
- Create: `backend/tests/integration/test_phase8_candidate_transaction.py`

**Interfaces:**

- `DeadlineReminderCandidateService.capture_for_event(session: Session, event: OpportunityEvent, *, created_at: datetime) -> tuple[UUID, ...]`.
- The service receives the existing transaction-owned `Session`; it never opens a session,
  commits, rolls back, checks publication or invokes an adapter.
- `OpportunityResolutionService._persist_plan()` flushes the event and calls the candidate service
  before its final flush.

- [ ] **Step 1: Write RED pure recognition tests**

Use fixed version contracts to prove only these two cases qualify:

```python
@pytest.mark.parametrize(
    ("before", "after", "direction"),
    [(date(2026, 9, 20), date(2026, 9, 10), "ADVANCED"),
     (date(2026, 9, 20), date(2026, 9, 30), "EXTENDED")],
)
def test_recognizes_one_exact_deadline_change(before, after, direction):
    intent = recognize_deadline_change(event_values(before, after))
    assert intent.direction.value == direction
```

Reject same date, null before/after, two changed fields, `UPDATED`, `CORRECTED`, `CANCELLED`,
`REOPENED`, `ATTACHMENT_REPLACED`, mismatched `changes`, non-consecutive versions and identity action
events.

- [ ] **Step 2: Write RED PostgreSQL audience and rollback tests**

Seed five users: saved+enabled+authorized, saved+disabled, unsaved+enabled, top-3-only+enabled and
saved+enabled with `ACTION_TRACKING` revoked. Assert only the first gets a
`WAITING_GOVERNANCE` candidate. Then test event-time action/preference/UserState snapshot binding,
no retroactive enable, unique replay, concurrent version resolution and injected candidate-insert
failure rolling back version, event, opportunity current version and every candidate.

- [ ] **Step 3: Run RED**

```powershell
Push-Location backend
uv run pytest tests/notifications/test_candidates.py -q
uv run pytest -m integration tests/integration/test_phase8_candidate_transaction.py `
  --strict-markers
Pop-Location
```

Expected: missing recognizer/capture service, then missing transaction hook.

- [ ] **Step 4: Implement recognition and latest-snapshot audience query**

The audience query must select the latest action per `(user_id, opportunity_id)`, latest preference
per `(user_id, DEADLINE_CHANGED)` and latest UserStateSnapshot per user in SQL, then filter
`saved=true`, `enabled=true` and `allowed_purposes` containing `ACTION_TRACKING`. Do not load all
historical rows and filter in Python. Bind the selected UserStateSnapshot ID and consent version.
Read old/current EvidenceRef IDs from the exact from/to OpportunityVersion `field_evidence` entries for
`application_window.closes_on`; require the event source evidence to remain governed by the
existing event/version constraints.

Construct one immutable intent per user and insert its operational row initially as:

```python
NotificationOutboxModel(
    status="WAITING_GOVERNANCE",
    attempt_count=0,
    lease_token=None,
    lease_until=None,
    next_attempt_at=None,
    **intent_columns,
)
```

- [ ] **Step 5: Add the minimum transaction hook**

Create the event object, add and flush it, call `capture_for_event(session, event,
created_at=created_at)`, then continue the existing Opportunity projection update. Do not alter
resolver classification or call the service for identity merge/split operations.

- [ ] **Step 6: Run GREEN and Phase 3 regression**

```powershell
Push-Location backend
uv run pytest tests/notifications/test_candidates.py tests/opportunities -q
uv run pytest -m integration tests/integration/test_phase8_candidate_transaction.py `
  tests/integration/test_phase3_resolution_replay.py --strict-markers
uv run ruff format --check src/deepaha/notifications/candidates.py `
  src/deepaha/opportunities/service.py tests/notifications/test_candidates.py
uv run ruff check src/deepaha/notifications/candidates.py `
  src/deepaha/opportunities/service.py tests/notifications/test_candidates.py
uv run mypy src/deepaha/notifications/candidates.py src/deepaha/opportunities/service.py
Pop-Location
git diff --check
```

- [ ] **Step 7: Exact commit and ordinary push**

Stage only Task 4 files, commit `feat: capture deadline reminder candidates`, and ordinary-push.

---

### Task 5: Implement governance gating, leased worker and test-inbox adapter

**Files:**

- Create: `backend/src/deepaha/notifications/adapters.py`
- Create: `backend/src/deepaha/notifications/worker.py`
- Create: `backend/src/deepaha/notifications/cli.py`
- Create: `backend/tests/notifications/test_worker.py`
- Create: `backend/tests/notifications/test_adapters.py`
- Create: `backend/tests/integration/test_phase8_worker_recovery.py`
- Create: `backend/tests/integration/test_phase8_public_governance.py`

**Interfaces:**

- `PostgresTestInboxAdapter.deliver(session: Session, intent: DeadlineChangeReminderIntentSchemaV07, *, delivered_at: datetime) -> TestInboxEntrySchemaV07`.
- `ReminderWorker.run_once(*, limit: int | None = None) -> ReminderWorkerRunSummary`.
- `ReminderWorkerRunSummary` contains only counts: inspected, promoted, claimed, delivered,
  suppressed, retried, failed and waiting_governance.
- CLI: `python -m deepaha.notifications.cli run-once --limit 50` with limits `1..100`.

- [ ] **Step 1: Write RED governance tests**

Seed an old governed PublicCatalogEntry and a new deadline version/event. Assert the candidate
stays `WAITING_GOVERNANCE`, creates zero attempts and creates zero inbox entries. Update the fixture
catalog entry to the exact complete/official `to_version`, then assert promotion. An unrelated,
incomplete, non-official or no-longer-current entry must not promote.

- [ ] **Step 2: Write RED lease, suppression and retry tests**

Use injected UUID/clock/adapter controls to prove:

```python
def test_retry_schedule_is_exact(worker, transient_adapter, clock) -> None:
    worker.run_once()
    assert outbox().attempt_count == 1
    assert outbox().next_attempt_at == clock.now + timedelta(minutes=1)
    clock.advance(minutes=1)
    worker.run_once()
    assert outbox().attempt_count == 2
    assert outbox().next_attempt_at == clock.now + timedelta(minutes=5)
    clock.advance(minutes=5)
    worker.run_once()
    assert outbox().status == "FAILED"
    assert outbox().attempt_count == 3
```

Also prove `FOR UPDATE SKIP LOCKED` single claim, lease-token ownership, expired lease recovery,
pre-delivery governance loss returning to wait, disable/unsave/`ACTION_TRACKING` revocation producing
terminal `SUPPRESSED`, permanent binding failure failing immediately, bounded error codes and no
retry-budget consumption for governance wait or lease expiry.

Capture logs for each failure path and assert they contain reminder/attempt IDs and stable codes but
not user-state values, consent contents, inbox bodies, cookies, bearer tokens or exception payloads.

- [ ] **Step 3: Write RED adapter crash/replay tests**

Prove inbox uniqueness by reminder ID and these two cases:

- failure before the database commit leaves no inbox, success attempt or delivered state;
- replay after a committed inbox insert returns the same entry and converges the Outbox to
  `DELIVERED` without a second inbox row.

- [ ] **Step 4: Run focused RED**

```powershell
Push-Location backend
uv run pytest tests/notifications/test_worker.py tests/notifications/test_adapters.py -q
uv run pytest -m integration tests/integration/test_phase8_worker_recovery.py `
  tests/integration/test_phase8_public_governance.py --strict-markers
Pop-Location
```

Expected: worker, adapter and CLI modules are absent.

- [ ] **Step 5: Implement the finite worker state machine**

Claim rows in a short transaction using `with_for_update(skip_locked=True)`, assign a UUIDv7 lease
token and commit the lease before adapter work. Process each claimed reminder in its own transaction
and update only when the persisted lease token matches. Use
`PublicCatalogService(session).get_opportunity(public_id)` and require returned
`current_version == to_version`; do not duplicate Phase 5 completeness logic.

Classify only explicit `TransientDeliveryError(code)` as retryable. Map validation/binding errors to
bounded permanent codes. The PostgreSQL adapter inserts immutable public/purpose-minimal fields and
uses its unique reminder ID for idempotent replay. Record the attempt and inbox/delivery state in
one transaction. A transient failure returns the row to `AVAILABLE` with exact `next_attempt_at`;
attempt 3 and permanent binding failures end in `FAILED` with no lease fields.

- [ ] **Step 6: Implement the bounded CLI**

The CLI obtains configured engine/session factory, injected UTC clock and the test adapter, runs
one batch and prints the count-only summary as sorted JSON. It accepts no user ID, opportunity ID,
provider, arbitrary payload or resend flag.

- [ ] **Step 7: Run GREEN and concurrency regression**

```powershell
Push-Location backend
uv run pytest tests/notifications/test_worker.py tests/notifications/test_adapters.py -q
uv run pytest -m integration tests/integration/test_phase8_worker_recovery.py `
  tests/integration/test_phase8_public_governance.py --strict-markers
uv run ruff format --check src/deepaha/notifications tests/notifications
uv run ruff check src/deepaha/notifications tests/notifications
uv run mypy src/deepaha/notifications tests/notifications
Pop-Location
git diff --check
```

- [ ] **Step 8: Exact commit and ordinary push**

Stage only Task 5 files, commit `feat: deliver governed reminders to test inbox`, and
ordinary-push.

---

### Task 6: Add owner-scoped test inbox reads

**Files:**

- Create: `backend/src/deepaha/notifications/inbox.py`
- Modify: `backend/src/deepaha/notifications/schemas.py`
- Modify: `backend/src/deepaha/api/reminders.py`
- Modify: `backend/tests/api/test_reminders.py`
- Create: `backend/tests/notifications/test_inbox.py`
- Create: `backend/tests/integration/test_phase8_inbox_isolation.py`

**Interfaces:**

- `ReminderInboxService.list_for_owner(principal: Principal, *, limit: int = 50) -> ReminderInboxPage`.
- `ReminderInboxPage(items: tuple[TestInboxEntrySchemaV07, ...], count: int)` with newest-first,
  stable `(delivered_at desc, inbox_entry_id desc)` order.
- Route: `GET /api/v1/me/reminder-inbox`; no write/read-receipt route.

- [ ] **Step 1: Write RED owner and read-only tests**

Assert the SQL query includes owner ID, returns at most 50 rows, has deterministic ordering and
does not load then filter. A foreign user's row is invisible. Snapshot the database before/after
GET and prove no timestamp, state or audit row changes.

```python
def test_get_inbox_has_no_open_or_read_side_effect(client, auth_header) -> None:
    before = phase8_table_hashes()
    response = client.get("/api/v1/me/reminder-inbox", headers=auth_header)
    assert response.status_code == 200
    assert phase8_table_hashes() == before
```

Assert `private, no-store`, fail-closed auth, bounded payload and absence of profile, consent,
opened, read, click and tracking fields.

- [ ] **Step 2: Run RED**

```powershell
Push-Location backend
uv run pytest tests/notifications/test_inbox.py tests/api/test_reminders.py -q
uv run pytest -m integration tests/integration/test_phase8_inbox_isolation.py --strict-markers
Pop-Location
```

Expected: inbox service and route are absent.

- [ ] **Step 3: Implement minimum inbox projection and route**

Map only immutable test-inbox columns into `TestInboxEntrySchemaV07`. Include opportunity public ID
and title, old/new dates, direction, event/from/to versions, prior/current official evidence,
detected/delivered times and the personal detail path. Do not add pagination, deletion, unread state,
search or delivery mutation.

- [ ] **Step 4: Run GREEN and personal API regression**

```powershell
Push-Location backend
uv run pytest tests/notifications/test_inbox.py tests/api/test_reminders.py `
  tests/api/test_personal.py tests/api/test_feedback.py -q
uv run pytest -m integration tests/integration/test_phase8_inbox_isolation.py --strict-markers
uv run ruff format --check src/deepaha/notifications/inbox.py src/deepaha/api/reminders.py
uv run ruff check src/deepaha/notifications/inbox.py src/deepaha/api/reminders.py
uv run mypy src/deepaha/notifications/inbox.py src/deepaha/api/reminders.py
Pop-Location
git diff --check
```

- [ ] **Step 5: Exact commit and ordinary push**

Stage only Task 6 files, commit `feat: expose owner scoped reminder inbox`, and ordinary-push.

---

### Task 7: Build the fixed Phase 8 vertical fixture and engineering report

**Files:**

- Create: `backend/tests/fixtures/reminders/phase8-deadline-reminder.json`
- Create: `backend/tests/fixtures/reminders/phase8-deadline-reminder.manifest.json`
- Create: `backend/tests/notifications/support.py`
- Create: `backend/tests/notifications/seed_phase8_browser.py`
- Create: `backend/tests/notifications/test_phase8_fixture.py`
- Create: `backend/tests/integration/test_phase8_vertical_slice.py`
- Create: `backend/tests/integration/test_phase8_transaction_rollback.py`

**Interfaces:**

- Fixture marker is exactly `SYNTHETIC_REMINDER_DELIVERY_ONLY`.
- Fixed scenario clock, IDs, old/new versions/evidence, four audience counterexamples and all
  expected engineering counts are declared in the manifest.
- Browser seeder prints fixture bearer token and expected Web route; it does not start a server.

- [ ] **Step 1: Author fixed fixture provenance and expected counts**

The fixture contains one saved+enabled+authorized user who receives one reminder, plus
saved+disabled, unsaved+enabled, ranked-only+enabled and purpose-revoked users who receive zero. It
contains one exact deadline-only event and non-qualifying multi-field/cancellation fixtures. All
content is synthetic and license-safe; the manifest explicitly declares real participants `0`,
human track `NOT_STARTED`, Release Qualification `NOT_STARTED` and
`HOLD_MISSING_HUMAN_EVIDENCE`.

- [ ] **Step 2: Write RED fixture and end-to-end tests**

The vertical test executes:

```text
seed v1 governed -> save -> enable -> resolve v2 deadline change
-> candidate WAITING_GOVERNANCE -> worker no delivery
-> fixture-govern v2 -> worker -> exactly one test inbox entry
-> API owner reads exact old/new evidence-bound result
```

Assert count-only engineering report values and exact trace replay. The rollback test injects
failures before candidate flush, after lease claim and before adapter commit, proving each recovery
invariant without synthetic open/read actions.

- [ ] **Step 3: Run RED and inspect only fixture/service expectation failures**

```powershell
Push-Location backend
uv run pytest tests/notifications/test_phase8_fixture.py -q
uv run pytest -m integration tests/integration/test_phase8_vertical_slice.py `
  tests/integration/test_phase8_transaction_rollback.py --strict-markers
Pop-Location
```

- [ ] **Step 4: Implement the deterministic support and seeder**

Reuse Phase 3/5/6 test support functions where importable; add only reminder-specific orchestration.
The fixture public-governance step updates the exact Phase 5 fixture catalog row and is labelled
test governance, not a new production approval service.

- [ ] **Step 5: Run GREEN and historical vertical regression**

```powershell
Push-Location backend
uv run pytest tests/notifications -q
uv run pytest -m integration tests/integration/test_phase8_vertical_slice.py `
  tests/integration/test_phase8_transaction_rollback.py `
  tests/integration/test_phase7_vertical_slice.py `
  tests/integration/test_phase6_vertical_slice.py --strict-markers
Pop-Location
git diff --check
```

- [ ] **Step 6: Exact commit and ordinary push**

Stage only Task 7 files, commit `test: add phase 8 reminder vertical fixture`, and ordinary-push.

---

### Task 8: Add the minimal Web preference and test-inbox experience

**Files:**

- Create: `web/lib/reminders.ts`
- Create: `web/app/reminder-actions.ts`
- Create: `web/components/reminder-preference-toggle.tsx`
- Create: `web/components/reminder-inbox-card.tsx`
- Create: `web/app/me/reminders/page.tsx`
- Create: `web/app/me/reminders/loading.tsx`
- Create: `web/app/me/reminders/error.tsx`
- Modify: `web/app/me/opportunities/page.tsx`
- Modify: `web/app/globals.css`
- Create: `web/tests/reminder-api-client.test.ts`
- Create: `web/tests/reminder-actions.test.ts`
- Create: `web/tests/reminder-preference-toggle.test.tsx`
- Create: `web/tests/reminder-inbox.test.tsx`
- Modify: `web/tests/status-states.test.tsx`

**Interfaces:**

- `getDeadlineReminderPreference() -> Promise<ReminderPreferenceSnapshot | null>`.
- `getReminderInbox() -> Promise<ReminderInboxPage>`.
- `setDeadlineReminderPreference(enabled: boolean, idempotencyKey: string) -> Promise<ReminderPreferenceSnapshot>`.
- Server action `toggleDeadlineReminderAction(formData: FormData) -> Promise<void>`.
- Route is `/me/reminders`; its visible heading contains `截止变化提醒测试收件箱`.

- [ ] **Step 1: Write RED typed-client and mutation tests**

Assert exact API paths, bearer forwarding through the existing personal session cookie, `no-store`,
PUT JSON `{enabled}`, a fresh Idempotency-Key and only `/me/reminders` revalidation. Reject extra
cadence/target form fields instead of forwarding them.

- [ ] **Step 2: Write RED component and route-state tests**

Assert copy stating “收藏不等于开启提醒”, fixed `尽快（精确版本通过治理后）` cadence and
`站内测试收件箱` target. Cards must render old/new deadline, `提前`/`延后`, detected time, official
evidence and personal action link. Test loading, disabled, empty, failure and populated states,
keyboard label/control association and absence of push/open-rate/complaint/retention claims.

- [ ] **Step 3: Run RED**

```powershell
Push-Location web
corepack pnpm test -- reminder-api-client reminder-actions reminder-preference-toggle reminder-inbox
Pop-Location
```

Expected: missing modules/components/routes.

- [ ] **Step 4: Implement the minimum server-rendered route**

Reuse the `deepaha_phase6_session` cookie path through `personalFetch`. Keep the toggle as a normal
labelled form/server action. Show the synthetic evidence boundary above the inbox. Add one link from
the personal action page to `/me/reminders`; do not add a notification badge, unread counter,
tracking call, polling loop or new global navigation hierarchy.

- [ ] **Step 5: Run Web GREEN and browser-quality regression**

```powershell
Push-Location web
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
corepack pnpm build
Pop-Location
git diff --check
```

Use the seeded Phase 8 fixture with the normal backend/Web development commands and Playwright or
manual Chromium smoke to verify 390px mobile and desktop widths, keyboard toggle, empty/populated
states and evidence/action links. Capture only engineering UI observations.

- [ ] **Step 6: Exact commit and ordinary push**

Stage only Task 8 files, commit `feat: add deadline reminder test inbox UI`, and ordinary-push.

---

### Task 9: Add isolated verifier and the ninth CI job

**Files:**

- Create: `scripts/verify-phase8.ps1`
- Create: `backend/tests/test_phase8_verifier_scope.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**

- Verifier accepts optional `ComposeProjectName`, otherwise uses `deepaha-phase8-$PID`.
- It owns only `infra/compose.phase8.yaml`, ports `55438/55006` and its exact Compose project.
- CI job name is exactly `phase8-deadline-reminder`.

- [ ] **Step 1: Write RED verifier-scope tests**

Assert the script rejects project names outside `^deepaha-phase8-[a-z0-9][a-z0-9-]*$`, checks
ports before start, uses exact project inspection, cleans only the exact project in `finally`,
clears Phase 8 environment variables and contains no command capable of stopping Phase 2-7
projects. Assert the printed evidence labels are exactly:

```text
SYNTHETIC_REMINDER_DELIVERY_ONLY
real participants=0
human track=NOT_STARTED
Release Qualification=NOT_STARTED
release decision=HOLD_MISSING_HUMAN_EVIDENCE
delivery target=TEST_INBOX
```

- [ ] **Step 2: Run RED**

```powershell
Push-Location backend
uv run pytest tests/test_phase8_verifier_scope.py -q
Pop-Location
```

Expected: verifier script is absent.

- [ ] **Step 3: Implement the verifier**

The verifier first runs `scripts/verify.ps1`, then starts only Phase 8 Compose, upgrades to head,
runs all contract/notification/reminder API tests, the exact Phase 8 integration set, empty
downgrade/re-upgrade/drift checks, Web lint/type/test/build and a seeded browser smoke. It must not
depend on a live model, network source, real provider or external identity.

- [ ] **Step 4: Add the branch trigger and isolated CI job**

Add `codex/phase-8-deadline-change-reminders` to push branches. The ninth job uses PostgreSQL
`55438`, Moto `55006`, Phase 8-only test credentials, Python/Node versions matching existing jobs,
and runs the same scoped checks. Preserve the eight inherited job names unchanged.

- [ ] **Step 5: Run focused GREEN, then the fresh full verifier**

```powershell
Push-Location backend
uv run pytest tests/test_phase8_verifier_scope.py -q
Pop-Location
$phase8Project = "deepaha-phase8-final-$PID"
powershell -ExecutionPolicy Bypass -File scripts/verify-phase8.ps1 `
  -ComposeProjectName $phase8Project
```

Expected: all checks pass; verifier cleanup leaves no exact Phase 8 project or listener on
`55438/55006`. Inspect actual output before making any success claim.

- [ ] **Step 6: Exact commit and ordinary push**

Stage only Task 9 files, commit `ci: verify phase 8 deadline reminders`, and ordinary-push.

---

### Task 10: Review the candidate and close only the Engineering Gate

**Files:**

- Create: `docs/gates/phase-8/README.md`
- Create: `docs/gates/phase-8/acceptance-results.md`
- Create: `docs/gates/phase-8/test-summary.md`
- Create: `docs/gates/phase-8/browser-verification.md`
- Create: `docs/gates/phase-8/security-and-compliance.md`
- Create: `docs/gates/phase-8/operations.md`
- Create: `docs/gates/phase-8/deferred-decisions.md`
- Create: `docs/gates/phase-8/engineering-metrics.md`
- Modify: `docs/development/system-roadmap.md`
- Modify: `docs/development/architecture.md`
- Modify: `docs/development/quality-and-release.md`

**Interfaces:** Gate documents bind the exact implementation candidate SHA, exact verifier output
and exact final GitHub Actions run/job results. They keep the three status axes separate.

- [ ] **Step 1: Perform a fresh full implementation review**

Compare every design section and plan task with the actual diff from exact base
`c7ae6ac1192e010b13a5b83c2e09347978839e7b`. Inspect transaction atomicity, latest-snapshot SQL,
Phase 5 governance reuse, composite integrity, lease ownership, attempt transactions, idempotent
adapter replay, owner filtering, error/log redaction, Web claims, migration downgrade and verifier
cleanup. Record concrete findings; fix reproducible defects with RED tests in separate commits and
rerun affected regressions before proceeding.

- [ ] **Step 2: Run verification-before-completion on a fresh Phase 8 runtime**

Run `scripts/verify-phase8.ps1` with a new project name, capture command, exit code, timestamps and
count-only report, then prove:

```powershell
git status --short
git diff --check
git merge-base --is-ancestor 151288574a44af43f147b5ddfd9ddf77ca3094ac HEAD
git ls-remote --heads origin codex/phase-8-deadline-change-reminders
```

The worktree must be clean and the exact upstream Phase 7 SHA must remain an ancestor.

- [ ] **Step 3: Write evidence without overstating it**

Record fixed engineering counts, retry/recovery/suppression results, migration evidence, browser
observations and scope exclusions. State explicitly:

- Implementation Status `IMPLEMENTED` only after code/tests exist;
- Engineering Gate remains `OPEN` until exact final candidate CI is successful;
- Release Qualification `NOT_STARTED`;
- real participants `0` and human result `HOLD_MISSING_HUMAN_EVIDENCE`;
- v0.7 `IMPLEMENTED`, not `STABLE`;
- target `TEST_INBOX`, not real notification delivery.

Do not copy roadmap open-rate or complaint-rate goals into achieved results.

- [ ] **Step 4: Commit and ordinary-push the candidate Gate package**

Stage only the listed Task 10 docs, inspect status language, commit
`docs: add phase 8 engineering gate evidence`, and ordinary-push. Do not create a PR or change an
existing PR.

- [ ] **Step 5: Verify the exact final CI candidate**

Observe the workflow triggered by the pushed exact SHA. Require these nine jobs to be successful:

```text
backend-quality
web-quality
integration
phase3-resolution
phase4-eligibility
phase5-public-trust
phase6-profile-action
phase7-feedback-review
phase8-deadline-reminder
```

If any job fails, inspect evidence, use systematic debugging, add a reproducing test where the
failure is a code defect, commit the minimum fix and rerun the entire final-candidate check. An
environmental failure does not become a false passing claim.

- [ ] **Step 6: Close only the Engineering Gate after exact-SHA evidence**

After all nine jobs succeed on the final exact SHA, update only the affected Phase 8 Gate status to
Engineering Gate `CLOSED`, keep Release Qualification `NOT_STARTED`, v0.7 `IMPLEMENTED` and all
human/production conclusions blocked. Commit `docs: close phase 8 engineering gate`, ordinary-push,
and require the docs-only SHA's final CI to pass before reporting closure.

- [ ] **Step 7: Stop at the authorized boundary**

Report exact branch, commits, verifier and final CI links, remaining Release Qualification risks,
and explicit deferred scope. Do not merge, mark ready, create a release, deploy, connect a real
provider or begin Phase 9.

---

## Plan Self-Review Checklist

- [x] Every included design requirement maps to Tasks 1-10.
- [x] Every explicitly deferred capability remains absent from every file list and interface.
- [x] All later interface names match the producer task exactly.
- [x] Every feature task contains RED, observed failure, minimum implementation, GREEN and exact
  commit/push steps.
- [x] No task modifies v0.1-v0.6 schema bytes or removes historical imports.
- [x] No task confuses governance waiting with delivery failure or retry budget.
- [x] No task lets a historical saved snapshot override current `ACTION_TRACKING` purpose.
- [x] No task records reads/opens or converts engineering counts into human metrics.
- [x] No task touches Phase 2-7 worktrees, runtimes, branches or draft PR state.
- [x] Gate closure requires fresh local evidence and exact-SHA success for all nine CI jobs.
- [x] Execution stops without merge, release, deployment, real provider or Phase 9 work.
