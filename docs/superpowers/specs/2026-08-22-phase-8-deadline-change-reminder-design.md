# DeepAha Phase 8 Deadline Change Reminder Design

## Document status

- Chat design approval: covered by the user's blanket authorization on 2026-08-22.
- Written design approval: covered by the same authorization; no additional approval pause is required.
- Exact upstream SHA: `151288574a44af43f147b5ddfd9ddf77ca3094ac`.
- Branch: `codex/phase-8-deadline-change-reminders`.
- Implementation Status: `PLANNED`.
- Engineering Gate: `OPEN`.
- Release Qualification: `NOT_STARTED`.
- v0.7 Contract Maturity: `PROPOSED`.

This document approves an architectural design and an implementation-planning boundary. It does
not claim that Phase 8 code, migrations, tests, delivery infrastructure, real-user evidence or
production notification behavior exists. The task stops after a separately committed
implementation plan unless the user authorizes implementation in a new task.

Phase 6 and Phase 7 human-participant Release Qualification remains independent of this Phase 8
engineering route. The current human-participant count remains zero and the applicable result
remains `HOLD_MISSING_HUMAN_EVIDENCE`. That does not block Phase 8 engineering design, but it still
blocks all corresponding human-action, trust, retention and production conclusions.

## 1. Goal

Design the smallest auditable Phase 8 vertical slice that turns one already-governed, high-impact
Opportunity change into one user-controlled reminder:

```text
OpportunityVersion + OpportunityEvent
  -> atomic reminder candidate
  -> exact-version public-governance wait
  -> bounded delivery worker
  -> deterministic test inbox
```

The slice proves engineering properties only: exact event/version/evidence binding, transactional
capture, duplicate suppression, retry and lease recovery, authorization, user control, public
trust gating, and deterministic test delivery. It does not build a general notification platform
and does not measure human opens, complaints, retention or actions.

## 2. Decision sources

This design follows, in priority order:

1. The user's Phase 8 task, approved reminder choices and blanket authorization.
2. `AGENTS.md`.
3. `文档2/DeepAha_青年机会智能系统_Blueprint_v1.2.docx`, especially the reminder,
   action, identity authorization, privacy, simulation/human-track and Gate sections.
4. The implemented v0.1-v0.6 contracts and Phase 1-7 Engineering Gate evidence.
5. `docs/development/system-roadmap.md`, `architecture.md` and
   `quality-and-release.md`.
6. The current repository behavior, including Phase 3 event persistence, Phase 5
   exact-version public catalog gating and Phase 6 server-derived user identity.

The Blueprint requires high-impact changes to be timely and user-controllable. The repository
architecture additionally requires a transactional Outbox, stable IDs, idempotency, bounded
retry and failure audit. The Blueprint does not itself name a transactional Outbox; this design
uses it because the repository architecture and current transaction boundary make it the minimum
reliable implementation.

## 3. Approved product semantics

### 3.1 Exactly one reminder variable

The first Phase 8 slice recognizes a reminder only when all of these conditions hold:

- `OpportunityEvent.event_type == DEADLINE_CHANGED`;
- `changed_fields` is exactly `{"application_window.closes_on"}`;
- the before and after deadline values are both present ISO dates;
- the dates differ;
- the event keeps the same stable `opportunity_id` and advances from one exact
  OpportunityVersion to another exact OpportunityVersion.

The reminder direction is deterministic:

- `ADVANCED` when the new closing date is earlier;
- `EXTENDED` when the new closing date is later.

The first slice excludes deadline creation from null, deadline removal to null, multi-field
changes, cancellation, reopening, corrections, attachment replacements, opportunity merge/split
events and every other change variable. This prevents multiple independent variables from being
mistaken for evidence about the deadline reminder.

### 3.2 Eligible audience

A user becomes a reminder candidate only when, at event-commit time:

1. the user's latest PersonalActionSnapshot for the stable opportunity has `saved == true`;
2. the user's independently versioned deadline-change reminder preference has `enabled == true`;
3. the bound opportunity and action data are owned by the server-derived authenticated user;
4. the event satisfies the exact rule in section 3.1.

Saving an opportunity is not notification consent. A preference enabled after the event does not
retroactively create a reminder candidate. An already-created candidate is suppressed before
delivery when the current preference is disabled or the opportunity is no longer saved.

Merely appearing in a top-three ranking, being eligible, viewing a detail page or submitting
feedback does not create reminder eligibility.

### 3.3 Cadence and delivery target

The first slice has one fixed cadence and one fixed target:

- cadence: deliver as soon as the event is governed and the worker can safely claim it;
- target: an authenticated in-product test inbox backed by PostgreSQL.

The user can turn this one reminder kind on or off. There is no daily or weekly digest, quiet-hour
configuration, frequency picker, real push, email, SMS, WeChat mini-program delivery, calendar
write, multi-channel routing or provider integration.

## 4. Options considered

### 4.1 Direct test-inbox insert

The Opportunity resolution transaction could insert directly into a test inbox. This is small,
but it cannot demonstrate retry, lease recovery or the required separation between event capture
and delivery. A delivery failure would either roll back the Opportunity transaction or require an
untracked second write. This option is rejected.

### 4.2 PostgreSQL transactional Outbox and test adapter

The Opportunity resolution transaction inserts immutable reminder candidates into a PostgreSQL
transactional Outbox. A bounded polling worker waits for exact-version public governance, claims
eligible rows with a lease, and writes through an idempotent test-inbox adapter. This reuses the
existing database, adds no queue service and proves the engineering properties required by the
repository architecture. This option is selected.

### 4.3 Redis/Celery multi-channel notification platform

A queue framework, provider adapters and channel orchestration could support future scale, but the
repository has no such runtime dependency and the first slice has one reminder variable and one
test target. This option expands operational and product scope before necessity is established.
It is rejected for Phase 8.

## 5. Public trust gate before delivery

### 5.1 Repository-specific constraint

`PublicCatalogEntry` is bound to an exact OpportunityVersion. When Phase 3 creates a new version
and event, the previous public-catalog approval does not approve the new version. A reminder must
not expose the new deadline before that exact `to_version` becomes the governed public version.

Creating the Outbox row only after publication would require a new approval hook and could lose
the original event-to-user side effect. Delivering immediately would bypass the Phase 5 public
trust boundary. The selected design therefore separates atomic capture from deliverability.

### 5.2 Governance wait

The event transaction creates the candidate in `WAITING_GOVERNANCE`. A worker may transition it to
`AVAILABLE` only when the current `PublicCatalogEntry`:

- references the same `opportunity_id` and exact `to_version`;
- satisfies the existing Phase 5 completeness and official-evidence rules;
- is visible through the existing public catalog service boundary.

Waiting for governance is not a delivery attempt and consumes no retry budget. The row remains
operator-auditable until governance appears. Phase 8 adds no catalog-approval API, operations
dashboard or automatic catalog mutation. Deterministic fixtures may promote the exact version by
the same fixture-level mechanism used by existing Phase 5 tests; that is engineering setup, not a
production approval workflow.

The worker rechecks the public gate immediately before test-inbox insertion. If approval was
removed or moved to another version, the row returns to `WAITING_GOVERNANCE` without a delivery
attempt.

## 6. Transaction boundaries and event capture

### 6.1 Atomic candidate creation

`OpportunityResolutionService._persist_plan()` already writes an OpportunityVersion and its
OpportunityEvent in one database transaction. Phase 8 extends that transaction after the event
row has an ID:

1. recognize only the exact event shape in section 3.1;
2. read latest saved action snapshots and latest enabled reminder preferences;
3. create at most one reminder candidate per eligible user;
4. commit version, event and all candidate rows together.

Any failure rolls back all four effects. A committed event cannot have a partially committed set
of candidates. Non-qualifying events do not create reminder rows.

Candidate generation uses the transaction's database view and a fixed clock. It stores the
preference snapshot and action snapshot IDs that justified inclusion. Later changes cannot rewrite
that historical reason.

### 6.2 Concurrency

The existing opportunity row lock serializes competing version updates for one opportunity.
Database uniqueness supplies the final defense against duplicate candidates. The transaction does
not call a delivery adapter, perform network I/O or wait for the worker.

## 7. Additive v0.7 contract

### 7.1 Necessity and compatibility

v0.1-v0.6 cannot express reminder preference history, delivery intent state, delivery attempts or
test-inbox entries without changing an existing schema. Phase 8 therefore proposes additive
`v0.7.0` contracts while preserving every committed byte and Python import path from v0.1-v0.6.

The contract starts `PROPOSED`. Passing fixed engineering evidence may advance it only to
`IMPLEMENTED`. It cannot become `STABLE` until the applicable Release Qualification is
`QUALIFIED`.

### 7.2 Contract types

The contract module defines deterministic enums and schemas for:

- `ReminderKind`: only `DEADLINE_CHANGED`;
- `DeadlineChangeDirection`: `ADVANCED` or `EXTENDED`;
- `ReminderCadence`: only `AS_SOON_AS_GOVERNED`;
- `ReminderTarget`: only `TEST_INBOX`;
- `ReminderPreferenceSnapshotSchemaV07`;
- `DeadlineChangeReminderIntentSchemaV07`;
- `NotificationOutboxStatus`;
- `NotificationDeliveryAttemptSchemaV07`;
- `NotificationDeliveryOutcome`;
- `TestInboxEntrySchemaV07`.

The intent binds:

- `reminder_id`, `user_id` and reminder kind;
- stable `opportunity_id`;
- exact `event_id`, `from_version` and `to_version`;
- exact old and new deadline values and derived direction;
- exact prior and current EvidenceRef identifiers;
- the qualifying PersonalActionSnapshot and preference snapshot;
- event detection time, candidate creation time and contract version;
- fixed cadence and fixed target.

No contract field claims that a user opened, acted on, trusted or retained because of a reminder.

## 8. Persistence model

Migration `0008` adds only Phase 8 structures and additive integrity constraints.

### 8.1 Reminder preference snapshots

`reminder_preference_snapshots` is append-only. Each user preference change creates a new row with
the user, reminder kind, enabled value, fixed cadence/target, predecessor snapshot, actor principal,
created time and contract version. The latest row is the effective preference.

No row is hard-deleted or updated. The first slice has no implicit default-on behavior; absence of
a snapshot means disabled.

### 8.2 Preference idempotency records

`reminder_preference_idempotency_records` follows the established Phase 6 authenticated command
pattern without changing Phase 6 tables. It binds user, route, idempotency key, request hash and
resulting snapshot. Replaying an identical command returns the original result; reusing a key for a
different body is rejected.

### 8.3 Notification Outbox

`notification_outbox` is a durable operational projection. It contains the immutable intent fields
and mutable delivery-control fields:

- status: `WAITING_GOVERNANCE`, `AVAILABLE`, `LEASED`, `DELIVERED`, `SUPPRESSED` or `FAILED`;
- `available_at`, `lease_token`, `lease_until` and `claimed_at`;
- `attempt_count`, `next_attempt_at`, `last_error_code` and terminal time;
- created and updated timestamps.

The database enforces one row for this logical delivery key:

```text
(user_id, event_id, to_version, reminder_kind, target)
```

The row has an exact OpportunityVersion foreign key and an event foreign key. An additive composite
uniqueness constraint on the event identity permits the database to prove that event,
`opportunity_id` and `to_version` agree. Services additionally verify `from_version`, deadlines and
evidence bindings before insert.

### 8.4 Delivery attempts

`notification_delivery_attempts` is append-only. Every real adapter invocation records attempt
number, lease token, start/end time, outcome, stable error code and adapter name/version. Error
details are bounded and sanitized; they cannot contain authorization headers, profile fields,
arbitrary exception representations or provider payloads.

Governance checks and user-control suppression are state decisions, not failed adapter attempts.

### 8.5 Test inbox entries

`test_inbox_entries` is immutable and owner-scoped. Its uniqueness on the reminder ID makes the
test adapter idempotent. It stores the exact user-facing payload plus all trace IDs needed to replay
the source event. Reading an entry never mutates an `opened_at` field because Phase 8 does not
define or measure opens.

## 9. Worker, idempotency and failure recovery

### 9.1 Claiming work

The worker is a bounded application command, not a remote administration endpoint. Each run:

1. promotes governed waiting rows to `AVAILABLE`;
2. reclaims expired leases;
3. claims a limited batch with `SELECT ... FOR UPDATE SKIP LOCKED`;
4. assigns a unique lease token and lease expiry;
5. processes only rows whose token it still owns.

All timing uses an injected clock. Batch size and lease duration have conservative settings
validated by configuration tests; they are not exposed as user-facing frequency controls.

### 9.2 Pre-delivery recheck

Immediately before adapter invocation, the worker verifies:

- the exact `to_version` is still the visible governed public version;
- the user's latest reminder preference is still enabled;
- the user's latest action snapshot for the opportunity is still saved;
- the immutable event, version, evidence and candidate bindings remain internally consistent.

Missing public governance returns the row to `WAITING_GOVERNANCE`. Preference-off or unsaved state
terminates it as `SUPPRESSED` with a stable reason code. Broken immutable bindings terminate it as
`FAILED` and require defect review; the worker never repairs facts silently.

### 9.3 Adapter atomicity

The test adapter writes the inbox entry and the worker writes the successful attempt and
`DELIVERED` state in one PostgreSQL transaction. If the process stops before commit, no success is
visible. If a crash occurs after a prior commit but before the caller observes it, replay sees the
unique inbox entry and converges to the same delivered result without a duplicate.

### 9.4 Retry policy

Only transient adapter failures consume retry budget. The first slice allows at most three total
adapter attempts:

- after attempt 1: retry after 1 minute;
- after attempt 2: retry after 5 minutes;
- after attempt 3: terminal `FAILED`.

Permanent validation errors fail immediately. Error classes are explicit and tested. A lease
expiry does not itself increment the attempt count unless an adapter invocation was durably
recorded. There is no unbounded retry loop and no manual resend endpoint in Phase 8.

## 10. Identity, authorization and privacy

### 10.1 Server-derived identity

All personal reminder routes reuse the Phase 6 server-derived `Principal` under `/api/v1/me`.
Neither path, query nor request body accepts an authoritative `user_id`. Fixture auth remains
fixture-only; Phase 8 does not create production identity.

### 10.2 Owner isolation

Preference and inbox reads are owner-filtered in the database query, not filtered after loading.
An unknown or foreign inbox identifier has the same not-found response. Responses use
`Cache-Control: private, no-store` and the established personal-route security headers.

### 10.3 Data minimization

The reminder payload contains only the opportunity title/public identity, old and new deadlines,
direction, evidence links, detected time and a personal detail link. It does not copy profile
answers, qualification facts, feedback, reviewer data or unrelated opportunity fields.

Audit records store purpose-limited IDs and stable reason/error codes. Logs must not emit test
inbox bodies, preference request bodies, user-state contents, cookies or authorization headers.

## 11. API design

### 11.1 Preference API

```http
GET /api/v1/me/reminder-preferences/deadline-change
PUT /api/v1/me/reminder-preferences/deadline-change
Idempotency-Key: <required for PUT>
```

The `PUT` body contains only `{ "enabled": true|false }`. The response also reports the fixed
cadence and target so the client cannot imply unsupported options. Identical idempotent replay
returns the original preference snapshot.

### 11.2 Test inbox API

```http
GET /api/v1/me/reminder-inbox
```

The first slice returns a bounded newest-first owner list. It supports no unread mutation, delete,
bulk action, search or delivery trigger. Each item exposes old and new deadlines, direction, exact
OpportunityEvent/Version trace, official evidence links, detected time and the existing personal
opportunity detail route.

### 11.3 No operational HTTP API

Worker execution is available only through a local/verification command. Phase 8 adds no public
send endpoint, administrative delivery endpoint, catalog approval endpoint, user lookup or bulk
notification API.

## 12. Minimal Web experience

The existing personal experience gains only:

- a clearly labelled deadline-change reminder switch;
- adjacent copy explaining that saving is separate from enabling reminders;
- an explicitly labelled in-product **test inbox**;
- an inbox card showing the opportunity, old deadline, new deadline, advanced/extended direction,
  last verified/detected time, evidence entry and next personal action link;
- loading, disabled, empty, failure and populated states;
- keyboard, focus, mobile and responsive behavior consistent with existing personal routes.

The UI must not call the inbox a push notification, WeChat message, calendar event or production
delivery. It must not display a fabricated match percentage, open rate, urgency score or human
behavior metric.

## 13. Engineering evidence and metric language

Phase 8 fixed fixtures may report only engineering measurements such as:

- qualifying and non-qualifying event counts;
- candidate, waiting-governance, delivered, suppressed and failed counts;
- duplicate-prevention and replay outcomes;
- attempt counts, retry schedule and lease recovery results;
- deterministic processing latency under a fixed clock;
- authorization denials and exact-version/evidence integrity results.

They must not be renamed or interpreted as human open rate, click rate, complaint rate, retention,
trust, conversion, application completion or action lift. A synthetic inbox read is not a human
open. A successful test adapter insert is not a delivered real push.

## 14. Test strategy

### 14.1 Contract and compatibility tests

- Export deterministic v0.7 schemas and one strict synthetic example.
- Prove enum rejection, exact evidence/version bindings and field constraints.
- Hash every v0.1-v0.6 schema before and after export and prove byte equality.
- Import every historical contract path without modification.

### 14.2 Event and transaction tests

- Create exact deadline-advanced and deadline-extended fixtures.
- Reject same-date, null transition, multi-field, cancellation, correction and attachment events.
- Prove version, event and all candidates commit atomically.
- Inject candidate-insert failure and prove no partial version/event commit.
- Prove one candidate per logical delivery key under replay and concurrency.
- Prove event-time enabled/saved selection and no retroactive enable behavior.

### 14.3 Governance tests

- Prove the new version remains `WAITING_GOVERNANCE` while only the old version is public.
- Prove no inbox row and no delivery attempt exists during that wait.
- Promote the exact `to_version` through fixture governance and prove it becomes deliverable.
- Remove or change governance before delivery and prove it returns to waiting.
- Prove an unrelated or incomplete public entry never authorizes delivery.

### 14.4 Worker recovery tests

- Prove two concurrent workers claim a row once.
- Prove expired-lease recovery with an injected clock.
- Prove successful replay cannot duplicate an inbox entry.
- Prove transient failures follow exactly the 1-minute/5-minute schedule and fail on attempt 3.
- Prove permanent validation failure does not retry.
- Prove disable or unsave before delivery produces audited `SUPPRESSED`.
- Prove governance wait and lease expiry do not incorrectly consume retry budget.

### 14.5 Authorization and API tests

- Prove server-derived owner isolation and foreign/unknown not-found equivalence.
- Prove preference idempotent replay and conflict behavior.
- Prove missing identity and unsupported auth modes fail closed.
- Prove `private, no-store` and existing personal-route headers.
- Prove inbox GET has no read/open side effect.

### 14.6 Web and browser tests

- Test switch semantics, copy, fixed target/cadence and all route states.
- Test old/new deadline and direction presentation without unsupported claims.
- Test keyboard operation, focus, mobile viewport and responsive layout.
- Run browser QA against fixed backend fixtures and capture no human-behavior conclusion.

## 15. Fixtures, isolation, verifier and CI

Phase 8 uses only fixed, permission-safe synthetic Opportunity, EvidenceRef, user, action,
preference and failure fixtures. It does not recruit participants or ingest real personal data.

The verifier uses a fresh isolated database/runtime distinct from Phase 2-7 workspaces and services.
Its exact ports, Compose project name, fixture IDs, fixed clock and cleanup ownership are declared in
the implementation plan and verifier. The architecture requires PostgreSQL only; Phase 8 does not
add Redis, Celery or a real provider.

The Phase 8 engineering candidate must retain all eight inherited required CI jobs and add one
isolated `phase8-deadline-reminder` job. The new job must cover migration upgrade/downgrade safety,
contract compatibility, backend integration, worker recovery, Web tests, browser smoke and the
fixed Phase 8 verification report.

Passing CI can close only the Phase 8 Engineering Gate. It cannot qualify a real delivery channel,
prove a human behavior metric, close Phase 6/7 human Release Qualification or promote v0.7 to
`STABLE`.

## 16. Migration and rollback safety

Migration `0008` must:

- add only Phase 8 tables, indexes, foreign keys and required additive uniqueness constraints;
- preserve all Phase 1-7 rows and schema-contract bytes;
- create indexes for event-time candidate lookup, governance waiting, available work, expired
  leases and owner inbox reads;
- reject inconsistent event/version references at the strongest practical database boundary;
- refuse downgrade while any Phase 8 table contains rows;
- downgrade cleanly only after those rows are intentionally absent;
- avoid triggers, destructive data rewrite and implicit preference backfill.

No existing user is silently opted in during migration.

## 17. Engineering Gate package

The future Phase 8 Engineering Gate may close only when a committed candidate contains:

- approved v0.7 contract exports and unchanged v0.1-v0.6 contract bytes/imports;
- migration `0008` upgrade, safe empty downgrade and non-empty downgrade refusal evidence;
- exact event/version/evidence and Phase 5 governance-gate tests;
- transaction, uniqueness, lease, retry, suppression and crash-replay tests;
- identity, idempotency, owner privacy and log-redaction tests;
- minimal Web experience and browser evidence;
- fixed-fixture verification report with engineering-only language;
- all inherited CI jobs plus the Phase 8 job successful on the final candidate SHA;
- a Gate document recording Implementation `IMPLEMENTED`, Engineering Gate `CLOSED`, Release
  Qualification `NOT_STARTED` and v0.7 `IMPLEMENTED` at most.

Any reproducible code, contract, migration, authorization or security defect found later requires
reassessment of the affected Engineering Gate. Missing human evidence by itself does not reopen it.

## 18. Explicitly deferred

Phase 8 does not implement or authorize:

- additional reminder variables or multi-variable experiments;
- real push, email, SMS, mini-program, calendar or provider credentials;
- Redis/Celery, multi-channel orchestration, templates, localization or provider failover;
- daily/weekly digest, quiet hours, frequency selection, escalation or snooze;
- production identity, public reviewer/admin identity or operations dashboard;
- catalog approval workflows or bypasses of exact-version public governance;
- click/open/read receipts, analytics pixels or human behavior claims;
- commercial ranking, pricing, payment, institution delivery or advertising;
- real participant recruitment, production deployment or compliance qualification;
- native App work, mini-program implementation or a general notification platform.

Any future addition requires independent necessity evidence and a new approved design.

## 19. Delivery and Git boundary

This design and its implementation plan are committed separately and pushed ordinarily on
`codex/phase-8-deadline-change-reminders`. This task must not:

- implement Phase 8 code, migration, fixture, test or UI behavior;
- change Phase 2-7 worktrees, branches or running environments;
- modify PR #6 or PR #8;
- merge, mark ready for review, rebase or force push;
- claim production readiness or create a production release.

## 20. Design success criteria

The design is complete when it makes these decisions unambiguous:

1. exactly one deadline-change variable is eligible;
2. saved state and independent opt-in are both required at event time;
3. version/event/candidate capture is atomic and idempotent;
4. exact `to_version` public governance is mandatory before delivery;
5. retry, lease, suppression and crash recovery are bounded and auditable;
6. the only target is an authenticated PostgreSQL test inbox;
7. no engineering result is described as a human behavior result;
8. Phase 8 engineering status is independent of Phase 6/7 human Release Qualification;
9. v0.7 begins `PROPOSED`, remains byte/import compatible with v0.1-v0.6, and can reach at most
   `IMPLEMENTED` on engineering evidence;
10. the next artifact is an implementation plan, not implementation code.
