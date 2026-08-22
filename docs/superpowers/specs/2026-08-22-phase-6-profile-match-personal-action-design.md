# DeepAha Phase 6 Profile, Match and Personal Action Design

> Date: 2026-08-22
>
> Design status: `APPROVED FOR IMPLEMENTATION`（用户已在当前任务中授权设计完成后持续执行，
> 无需常规人工 review checkpoint）
>
> Exact upstream: Phase 5 final head
> `8d9b36c96174bffb303e7f981bd1775ebd8fa672`
>
> Startup axes: Implementation `NOT_STARTED`; Engineering Gate `OPEN`; Release Qualification
> `NOT_STARTED`; Phase 6 Contract Maturity `PROPOSED`

## 1. Purpose and bounded outcome

Phase 6 delivers the first authenticated, user-isolated vertical slice from a Phase 5 public
Opportunity to an immutable progressive profile, a reproducible v0.4 eligibility MatchSnapshot, a
separate deterministic priority order, and a minimal personal action record.

This phase improves the `判断 -> 行动` parts of `可信发现 -> 判断 -> 行动 -> 学习`. It does not
implement the Phase 7 feedback/review loop or Phase 8 reminders and notifications.

The minimum successful engineering outcome is:

1. a user can save only the minimum profile facts needed now, explicitly skip optional facts, and
   preserve missing values as unknown;
2. every personal request derives its subject from a server-side authenticated principal and never
   trusts a caller-supplied `user_id`;
3. a personal match fixes the exact OpportunityVersion, RuleSet, user-state/profile snapshot,
   scenario clock and Phase 4 component versions and produces the existing four-state result;
4. eligibility and ranking are separate persisted outputs, and changing only soft preferences can
   change order but not any eligibility status or v0.4 MatchSnapshot input;
5. a user can see a deterministic 90-day view with no more than three priority items, understand
   satisfied/conflicting/missing facts, inspect official EvidenceRefs, and return to the official
   application URL;
6. save, official-link intent, material plan and explicit action state writes are idempotent,
   user-isolated and audited;
7. API, responsive Web/PWA, browser verification, migration, verifier, CI and Gate evidence support
   Engineering Gate closure without claiming real-user qualification.

## 2. Decision sources and inherited invariants

This design is derived from the current task, `AGENTS.md`, Blueprint v1.2, the reconciled Blueprint
baseline, the system roadmap Phase 6 entry, architecture and quality documents, v0.1-v0.4 domain
contracts, and Phase 1-5 design/plan/Gate evidence.

The following inherited invariants remain unchanged:

- `Source -> RawArtifact -> Document -> Opportunity -> Version / Event -> RuleSet -> Match -> Action`.
- `Document != Opportunity`; personal results bind to a stable Opportunity and exact version.
- original evidence is immutable and every hard result remains traceable to official EvidenceRefs.
- eligibility only uses `ELIGIBLE`, `LIKELY_ELIGIBLE`, `UNCERTAIN`, `INELIGIBLE`.
- `INELIGIBLE` still requires a deterministic conflict backed by official evidence.
- missing, skipped, ambiguous or conflicting data never defaults to `INELIGIBLE`.
- soft preference ranking cannot alter or mask an eligibility result.
- no percentage, model confidence or semantic similarity is presented as eligibility or priority.
- v0.1-v0.4 Schema files and Python import paths remain byte/import compatible.
- Phase 5 remains Implementation `IMPLEMENTED`, Engineering Gate `CLOSED`, Release Qualification
  `NOT_STARTED`, Public API Contract Maturity `IMPLEMENTED` and not `STABLE`.
- the three Phase 5 records and all Phase 6 user/action fixtures are license-safe synthetic data,
  never real Gold or real-user evidence.

## 3. Scope

### 3.1 In scope

- additive v0.5 contracts for user-state snapshots, ranking snapshots and action snapshots/events;
- an immutable personal user-state store and a v0.5 nullable non-synthetic qualification
  projection;
- a bounded non-production authentication session boundary with bearer-token digest lookup;
- exact owner scoping and non-enumerating personal errors;
- reuse of approved v0.4 RuleSet, compiler, deterministic Eligibility Engine and MatchSnapshot;
- a deterministic 90-day candidate view and at most three priority items;
- explicit explanations for satisfied, conflicting and unknown rules plus official evidence links;
- idempotent save, official-link-open intent, material checklist and action-state writes;
- progressive profile, result list/detail and action UI with loading, empty, failure and uncertainty
  states at mobile and desktop widths;
- fixed generated fixtures, backend/frontend/integration/contract/security tests, Phase 6 verifier,
  isolated compose project, CI job, browser evidence and Gate package.

### 3.2 Explicitly out of scope

- Phase 7 `FeedbackEvent`, correction adjudication, Review Queue, reviewer SLA, label release or
  feedback-driven rules/prompt/ranking updates;
- Phase 8 outbox, reminders, push, notification preferences, Mini Program, calendar or multi-device
  delivery;
- production login, registration, credential recovery, MFA, social identity or external IdP;
- LLM/Model Gateway, semantic eligibility, vectors, Redis/Valkey/Celery, collection expansion,
  Docling/OCR, commercial ranking, payment, production cloud, production release or PR merge;
- Phase 5 real Gold collection or its Release Qualification;
- any real-user completion/action metric, contract `STABLE` promotion, ready-for-review or merge.

## 4. Alternatives considered

### 4.1 Mark user profiles as synthetic v0.4 fixtures

This would fit the existing Phase 4 database check but would falsify provenance and allow real-user
engineering evidence to be confused with simulation. It is rejected.

### 4.2 Build a second eligibility and match persistence path

A parallel Phase 6 eligibility result would duplicate the v0.4 engine and MatchSnapshot truth,
creating drift in status rules, evidence protection and replay. It is rejected.

### 4.3 Accept `user_id` in personal URLs or request bodies

Even with application checks, a public identifier is forgeable and invites insecure direct object
reference (IDOR) bugs. It is rejected. Personal routes use `/me` and the server-resolved principal.

### 4.4 Selected approach: additive v0.5 user/action contracts plus v0.4 match reuse

Phase 6 adds the domain objects absent from v0.4 and links each immutable `UserStateSnapshot` to a
non-synthetic v0.5 qualification projection stored in the existing `profile_snapshots` table.
Migration `0006` replaces only the database-level synthetic/schema-version provenance check; it
keeps v0.4 profile Schema bytes unchanged. The existing Phase 4 service continues to reject
non-synthetic inputs. A new owner-aware personal service may evaluate the linked projection and
persists the ordinary v0.4
EligibilityResult and MatchSnapshot. Ranking and action data remain separate v0.5 records.

This provides one qualification truth while retaining an explicit provenance boundary.

## 5. Identity, authorization and privacy boundary

### 5.1 Non-production session model

The repository has no production identity infrastructure. Phase 6 therefore implements a bounded
engineering session adapter, not a production authentication claim:

- requests send `Authorization: Bearer <opaque-session-token>`;
- only `SHA-256(token)` is stored and compared; plaintext tokens are neither persisted nor logged;
- the digest resolves one internal `user_id`, expiry and revocation state on the server;
- session fixtures are inserted only by a Phase 6 seed/test helper in disposable environments;
- there is no HTTP endpoint for creating accounts or sessions;
- outside explicitly configured `development`/`test` Phase 6 mode, personal routes fail closed until
  a production identity adapter exists.

This proves server-side principal derivation, isolation and error handling. It is not registration,
login, credential lifecycle or public-launch readiness.

### 5.2 Owner scope

Personal routes are under `/api/v1/me`; no route, query or body accepts `user_id`. Service methods
require a `Principal` produced by the authentication dependency. Every select/update includes the
resolved `user_id`; foreign keys and uniqueness constraints retain the same boundary at persistence.

An object belonging to another user and a nonexistent object return the same generic `404` problem.
Responses expose no owner ID, session digest, consent audit actor, database key belonging to another
user, SQL or stack trace. Missing/invalid/expired/revoked credentials use one generic `401` response.

### 5.3 Data minimization and control

The first profile asks only for life stage, education, major, graduation year, current/target region
and current opportunity goal. Age/birth date, hukou, certificates and similar fields remain absent
until an approved rule requires them. Every optional field can be omitted or explicitly recorded in
`skipped_fields`; omission and skip both project to `None`, never to a conflicting value.

The immutable snapshot records consent version, allowed purposes and personalization switch. Phase 6
supports viewing and replacing the current snapshot; actual account/profile deletion is deferred
until a governed destructive-data workflow is designed. The UI states that limitation honestly.
No name, phone, email, government identifier or free-form biography is accepted.

## 6. v0.5 contract family

`backend/src/deepaha/contracts/phase6.py` and `contracts/schemas/v0.5.0/` add only new types while
re-exporting none of the prior files. Historical v0.1-v0.4 files remain byte-identical.

### 6.1 `UserStateSnapshotSchemaV05`

| Field | Constraint / meaning |
|---|---|
| `user_state_snapshot_id` | UUIDv7 immutable snapshot identity |
| `user_state_id` | stable UUIDv7 identity for one user's state stream |
| `version` | positive, monotonically increasing per user-state |
| `qualification_profile_snapshot_id` | exact non-synthetic v0.5 profile projection |
| `life_stage` | finite optional user context; not a hard rule by itself |
| `goal_types` | finite non-empty set when provided |
| `attributes` | v0.5 nullable qualification attributes over the same finite v0.4 rule fields |
| `preference_regions` / `preference_types` | optional soft-ranking inputs only |
| `skipped_fields` | unique finite field names explicitly skipped |
| `personalization_enabled` | false disables soft preferences, not qualification |
| `consent_version` / `allowed_purposes` | explicit versioned purpose record |
| `scenario_clock` | fixed date used by profile projection and match window |
| `input_sha256` | canonical hash for idempotent identical snapshots |
| `created_at` | audit instant |

`UserProfileAttributesSchemaV05` preserves the v0.4 field names and controlled scalar values but
makes every field, including `target_regions` and `certificates`, nullable. This distinction is
required because the Phase 4 engine interprets `None` as unknown while an empty set is a known value
that may deterministically conflict. The contract rejects sensitive/unknown keys, duplicate set
values, contradictory “skipped and provided” fields, an empty purpose set, or a scenario clock that
differs from its qualification projection.

### 6.2 `PersonalRankingSnapshotSchemaV05`

One ranking snapshot fixes:

- user-state snapshot and qualification profile snapshot IDs/versions;
- scenario clock and inclusive 90-day window end;
- ranker version and canonical input hash;
- ordered items, each linked to an exact v0.4 MatchSnapshot and OpportunityVersion;
- eligibility status copied for display validation, ordinal priority and finite reason codes.

The contract permits no score, percentage, probability, confidence or model field. It validates at
most three items, consecutive ordinals starting at one, unique opportunities and exact window dates.
`INELIGIBLE` items may be inspected in a single-opportunity fit check but never enter priority items.

### 6.3 `PersonalActionSnapshotSchemaV05`

One current action snapshot contains the owner-scoped Opportunity ID, saved flag, explicit state,
bounded material checklist, version and last event identity. States are:

- `NOT_STARTED`
- `PREPARING`
- `APPLIED`
- `COMPLETED`
- `DISMISSED`

Audit events are limited to `SAVED_CHANGED`, `OFFICIAL_LINK_OPENED`, `MATERIAL_PLAN_CHANGED` and
`ACTION_STATE_CHANGED`. They are append-only and contain structured values only. There is no
feedback text, correction verdict, reviewer state, reminder schedule or notification field.

## 7. Persistence model and migration

Migration `20260822_0006` is additive except for replacing the Phase 4 synthetic-only and v0.4-only
profile checks with one provenance check: synthetic rows require `profile_schema_version = 0.4.0`,
and non-synthetic rows require `profile_schema_version = 0.5.0`. Existing v0.4 rows, columns, keys
and data remain unchanged.

### 7.1 Tables

- `personal_users`: internal UUIDv7 identity, stable user-state ID, created time and active flag;
- `personal_auth_sessions`: token digest primary key, restrictive user FK, expiry/revocation and
  created time;
- `user_state_snapshots`: immutable owner/version rows, linked qualification profile snapshot,
  minimized fields, consent, canonical hash and times;
- `personal_ranking_snapshots`: immutable owner/snapshot/window/ranker/hash rows;
- `personal_ranking_items`: ordered exact OpportunityVersion + v0.4 MatchSnapshot references;
- `personal_action_snapshots`: versioned owner/opportunity action state and material plan;
- `personal_action_events`: append-only owner/action event records;
- `personal_idempotency_records`: owner + operation + key digest, request hash and exact response
  reference for safe replay.

All personal foreign keys use `RESTRICT`; owner/version and idempotency uniqueness is enforced in the
database. JSON values have type checks and bounded application schemas. Token or idempotency-key
plaintext is never stored. Downgrade refuses while any Phase 6 personal row or non-synthetic profile
projection exists, preventing silent evidence deletion.

### 7.2 Profile projection

Saving a UserState snapshot creates one `profile_snapshots` row with:

- `synthetic = false`;
- attributes validated by `UserProfileAttributesSchemaV05`; absent scalar and set fields are stored
  as JSON null so the existing engine evaluates them as unknown;
- the same scenario clock;
- `profile_schema_version = 0.5.0`, making personal provenance mechanically distinct from v0.4
  synthetic fixtures;
- non-sensitive provenance markers identifying self-service creation, never a fake human review.

The projection is immutable and ownership is proven only through its restrictive link from the
owner-scoped UserState snapshot. Phase 4 `evaluate_and_save` retains its synthetic-only guard.

## 8. Matching and ranking

### 8.1 Exact match input

For each governed public candidate, the personal match service fixes:

- Phase 5 allowlisted current OpportunityVersion;
- the approved RuleSet belonging to that exact version;
- the current UserState snapshot and linked v0.5 qualification profile projection;
- the snapshot scenario clock;
- compiler, eligibility engine, major catalog and approved mapping versions;
- semantic-major-candidate `false`.

The service calls the same compiler and deterministic engine as Phase 4 and persists the same v0.4
EligibilityResult/MatchSnapshot shape. A replay reads the persisted snapshot; a rerun with identical
input resolves the same `input_sha256` record.

If an otherwise visible opportunity has no exact approved RuleSet, it is not silently treated as
eligible. The single fit-check returns `UNCERTAIN` with a governed `RULE_SET_UNAVAILABLE` reason and
official opportunity evidence, while the bulk priority run omits it from actionable top-three and
reports the omission count.

### 8.2 Four-state explanation

The personal result maps v0.4 rule evaluations without changing them:

- satisfied rules -> “已满足” with reason and official EvidenceRef;
- deterministic official conflicts -> “存在冲突” with reason and official EvidenceRef;
- unknown rules/missing fields -> “仍需确认” with the exact missing field;
- review reasons -> visible risk notes, never hidden behind an overall score.

Every result also includes current deadline/change markers, last verification time, official
application URL and evidence links derived from Phase 5. No raw storage URL is exposed.

### 8.3 Deterministic 90-day view

Candidates must be Phase 5 visible/current, status `OPEN` or `CLOSING_SOON`, and have an inclusive
deadline between scenario clock and scenario clock + 90 days. The fixed ranker produces priority
items only from `ELIGIBLE`, `LIKELY_ELIGIBLE` and `UNCERTAIN`.

Ordering is lexicographic and versioned:

1. eligibility actionability band (`ELIGIBLE`, `LIKELY_ELIGIBLE`, `UNCERTAIN`);
2. explicit preference-region match when personalization is enabled;
3. explicit preference-type match when personalization is enabled;
4. earlier deadline;
5. stable Opportunity public ID.

Only the first three items are returned as priorities. The API returns reason codes for each ordering
component, not a numeric score. With personalization disabled, preference components are neutral.
Changing only preferences reuses the same eligibility MatchSnapshots and may only alter ordering and
ranking reasons.

## 9. Personal API contract

All routes require the authenticated principal and return `Cache-Control: private, no-store`.

- `GET /api/v1/me/profile` returns the current immutable snapshot or generic `404`;
- `PUT /api/v1/me/profile` creates/reuses an immutable snapshot from minimized structured input;
- `POST /api/v1/me/matches` creates/reuses the current 90-day ranking snapshot;
- `GET /api/v1/me/opportunities` returns the latest ranking and at most three priorities;
- `GET /api/v1/me/opportunities/{public_id}` returns the owner-scoped personal explanation;
- `PUT /api/v1/me/opportunities/{public_id}/saved` changes/reuses saved state;
- `POST /api/v1/me/opportunities/{public_id}/official-link` records intent and returns the governed
  official URL for client navigation;
- `PUT /api/v1/me/opportunities/{public_id}/material-plan` changes/reuses the bounded checklist;
- `PUT /api/v1/me/opportunities/{public_id}/status` changes/reuses explicit action state.

Every write requires an `Idempotency-Key` of 16-128 visible ASCII characters. The server stores only
its digest. Repeating the same owner/operation/key and canonical request returns the original result;
reusing it with different input returns non-sensitive `409`. Unknown and other-user resources use
the same `404`. Validation uses generic field-safe `400`; dependencies use generic `503`.

No endpoint accepts user IDs, arbitrary rule/catalog/mapping versions, arbitrary result status,
free-form feedback, reminder time or notification address.

## 10. Web/PWA experience

### 10.1 Information architecture

- `/profile`: privacy-first progressive form, optional skip controls and current snapshot summary;
- `/me/opportunities`: deterministic 90-day result state and at most three priority cards;
- `/opportunities/[publicId]/fit-check`: authenticated single-opportunity fit check replacing the
  Phase 5 static boundary;
- `/me/opportunities/[publicId]`: explanation, evidence, official link, save, action state and
  material checklist.

The Phase 5 public list/detail remains usable without personal credentials. Its fit-check entry
clearly crosses into a private no-store flow.

### 10.2 UI and accessibility constraints

The `ui-ux-pro-max` review is used as a constraint check, not as authority to replace the Phase 5
brand language. Phase 6 keeps the trusted blue/deep-sea blue, restrained orange discovery emphasis,
cards, whitespace and text wordmark. It adopts:

- semantic landmarks, one `h1`, visible labels/helper/error text and predictable back links;
- progressive disclosure rather than one large sensitive form;
- at least 16px body text, 44px touch targets, 8px control spacing and visible focus rings;
- no color-only state; every eligibility/action state has text and supporting explanation;
- mobile-first layouts with no horizontal scroll at 375px and clear desktop hierarchy at 1440px;
- route `loading.tsx`, `error.tsx`, honest empty states and focus movement/announcements after writes;
- reduced-motion support and no decorative animation dependency;
- explicit synthetic-fixture and privacy/non-production identity notices;
- no watermarked `logo.png`, invented logo, fake metric, fake user story or marketing number.

## 11. Failure modes and safe behavior

| Failure | Safe behavior |
|---|---|
| missing/invalid/expired session | generic `401`; no existence or profile hint |
| other-user or unknown personal object | identical generic `404` |
| caller supplies unknown fields or `user_id` | reject request; do not ignore silently |
| optional qualification fact absent/skipped | persist `None`; eligibility can only remain eligible/likely/uncertain as v0.4 rules allow |
| current Opportunity version differs from governed version | omit/reject until governance catches up |
| exact approved RuleSet absent | explicit uncertainty; never infer eligibility |
| idempotency key reused with different request | generic `409`; no second write |
| transaction failure | rollback profile/action/audit together; generic `503` |
| ranking rerun with identical fixed inputs | reuse canonical snapshot |
| public official URL invalid or credentials embedded | reject/omit personal result; never return unsafe URL |
| frontend API failure | error state with retry/back path; never turn it into “no opportunities” |

## 12. Verification strategy

Implementation follows task-level `RED -> minimum implementation -> targeted verification ->
risk-proportionate regression -> exact-file commit -> normal push`.

### 12.1 Contract and compatibility tests

- v0.5 Schema/Pydantic parity, frozen shapes, forbidden extra/sensitive/percentage fields;
- v0.1-v0.4 manifest bytes and import paths unchanged;
- UserState skip/provided contradictions, versions, hashes and consent controls;
- ranking max-three/window/order/unique/link constraints and action finite states.

### 12.2 Backend and integration tests

- migration upgrade/downgrade refusal/re-upgrade/drift;
- bearer digest resolution, expiry/revocation and log/response secret absence;
- missing-token, other-user and unknown-object negative cases;
- immutable profile versions, identical-save reuse and optional-field unknown projection;
- exact OpportunityVersion/RuleSet/Profile/scenario/component binding and deterministic replay;
- all four eligibility states and official evidence links;
- preference counterfactual: order changes while eligibility and v0.4 snapshots do not;
- inclusive 90-day boundaries, excluded statuses, omitted rule-set case and at most three priorities;
- save/official-link/material/status idempotency and audit atomicity;
- negative assertions for percentage/confidence/LLM, Phase 7 feedback and Phase 8 notification shapes.

### 12.3 Web and browser tests

- component/route tests for progressive profile, skip, four states, evidence, save/action and
  loading/empty/error/uncertain states;
- semantic labels, focus, keyboard operation and privacy/fixture notice assertions;
- real Chromium verification of public detail -> fit check -> profile -> 90-day priorities ->
  personal detail -> save -> material/action -> official link at desktop and mobile viewports;
- keyboard-only pass and one API failure/recovery pass;
- browser evidence records commands, fixture identity and observations only; screenshots, storage,
  cookies and session state are untracked artifacts and are deleted after review.

### 12.4 Isolated verifier and CI

`infra/compose.phase6.yaml` uses only PostgreSQL `127.0.0.1:55436`, Moto
`127.0.0.1:55004` and exact projects matching `deepaha-phase6-*`. The verifier checks port ownership
before startup and cleans only its exact project. It never enumerates, connects to, stops or reuses
Phase 2/3/4/5 services or ports.

`scripts/verify-phase6.ps1` runs the root regression, v0.5/profile/matching/action/API tests,
integration tests, migration cycle, Web tests/build, verifier scope checks and bounded synthetic
evaluation. CI adds one `phase6-profile-action` job while retaining all six inherited jobs.

## 13. Engineering Gate and Release Qualification

### 13.1 Engineering Gate closure requirements

Engineering Gate may move to `CLOSED` only after all of the following are evidenced for one final
exact SHA:

- implementation, v0.1-v0.4 compatibility and v0.5 `IMPLEMENTED` evidence;
- additive/reversible migration with protected-data downgrade refusal;
- identity/authorization/isolation/privacy negative tests;
- deterministic eligibility/ranking/action API and responsive Web/PWA;
- local tests, synthetic evaluation, real-browser desktop/mobile/keyboard/failure recovery;
- scope, secret, artifact, license, privacy, authorization and full-diff reviews;
- task-level commits normally pushed to the Phase 6 branch;
- open/draft/unmerged stacked PR based on `codex/phase-5-public-trust-layer`;
- every required GitHub Actions job successful on the final exact SHA.

### 13.2 Four axes at engineering closure

- Implementation: at most `IMPLEMENTED`.
- Engineering Gate: `CLOSED` only with the evidence above.
- Release Qualification: expected `NOT_STARTED`.
- Phase 6 Contract Maturity: at most `IMPLEMENTED`, never `STABLE`.

### 13.3 Release Qualification evidence still required

The minimum-profile completion rate `>=60%`, understanding/trust/cognitive-load observations and at
least one real high-intent action must come from 20-30 consented design partners through a governed
real-user protocol. Synthetic profiles, browser actions, fixture completion rates and CI cannot
start or satisfy that qualification. Gate D and production release therefore remain outside this
engineering phase.

## 14. Commit and stacked delivery strategy

Phase 6 uses independent, reviewable commits in this order:

1. approved design;
2. executable task plan;
3. v0.5 contracts and backward-compatibility tests;
4. migration, authenticated principal and immutable UserState;
5. personal v0.4 match reuse and deterministic ranking;
6. idempotent actions and personal API;
7. Web/PWA personal flows and unit tests;
8. isolated verifier, synthetic fixtures, integration/CI and browser verification;
9. Gate evidence, reviews and exact-candidate closure updates.

Each commit stages exact related paths only and is pushed normally. The final draft PR uses base
`codex/phase-5-public-trust-layer` and head `codex/phase-6-profile-match-personal-action`; it remains
open, draft and unmerged.
