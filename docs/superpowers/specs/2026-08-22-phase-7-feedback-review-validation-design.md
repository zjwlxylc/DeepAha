# DeepAha Phase 7 Feedback, Review and Dual-track Validation Design

## Document status

- Design approval: approved by the user on 2026-08-22.
- Exact upstream SHA: `7f2cebc2afcfc6cb7061ed5bb91d79b824e91a3d`.
- Branch: `codex/phase-7-feedback-review-validation`.
- Implementation Status: `IMPLEMENTED`.
- Engineering Gate: `CLOSED`.
- Release Qualification: `NOT_STARTED`.
- v0.6 Contract Maturity: `IMPLEMENTED` (not `STABLE`).

This is the approved design realized by exact engineering candidate
`63536985d5b03b3ad5dbb5bea1cf82120ee866fc`. GitHub Actions run `32571667136` completed all eight
required jobs successfully, closing only the Engineering Gate. The implementation and fixed
synthetic evidence are not Release Qualification evidence, a production authorization or a
contract-stability claim.

## 1. Goal

Build the smallest auditable Phase 7 vertical slice that can receive an authenticated user's
structured correction about an exact historical match, preserve the raw event immutably, route it
through a purpose-limited human review process, create a separately governed label asset, and carry
one improvement direction through offline and shadow candidate gates without changing any online
RuleSet, MatchSnapshot, eligibility decision or personal ranking.

The engineering slice must also encode the separation between simulation evidence and consented
human-participant evidence. Phase 7 uses only fixed, permission-safe synthetic feedback fixtures;
therefore the human track and Release Qualification remain `NOT_STARTED`.

## 2. Decision sources

This design follows, in priority order:

1. The user's Phase 7 task and explicit exclusions.
2. `AGENTS.md`.
3. `文档2/DeepAha_青年机会智能系统_Blueprint_v1.2.docx`, especially chapters 5–7, 9–10,
   12, 15–17 and appendices B–D.
4. The implemented v0.1–v0.5 contracts and Phase 1–6 Engineering Gate evidence.
5. `docs/development/system-roadmap.md`, `architecture.md` and `quality-and-release.md`.

The Blueprint requires this learning chain:

```text
Raw Feedback -> Consent -> Evidence Link -> Confidence -> Review/Adjudication
  -> Label Asset -> Offline Evaluation -> Update Candidate -> Shadow Test -> Release Gate
```

The chain is a governance sequence. It does not authorize online training or direct mutation of a
production decision component.

## 3. Scope

### 3.1 Included

- Additive v0.6 feedback/review/validation contracts with deterministic JSON Schema export.
- Immutable, authenticated FeedbackEvent persistence.
- Exact binding to the owner's original MatchSnapshot, OpportunityVersion, ranking snapshot,
  user-state snapshot and submission-time contract/consent versions.
- Append-only EvidenceRef supplements restricted to evidence already governed for the bound
  OpportunityVersion.
- A versioned Review Queue projection, separate confidence assessment and append-only human
  adjudication.
- A separately persisted approved label asset that can only follow confirmed human adjudication.
- Exactly one selected improvement direction in a Phase 7 validation cycle.
- Separate offline evaluation candidate, shadow candidate and release-gate decision records.
- Different simulation and human-participant dataset contracts, metrics and conclusion language.
- Minimal user correction/status Web flow and minimal controlled reviewer Web flow.
- Fixed CC0 synthetic fixtures, PostgreSQL integration tests, browser QA, isolated verifier, CI and
  Phase 7 Gate evidence.

### 3.2 Explicitly excluded

- Phase 8 reminder, notification, Outbox, push, mini-program or calendar behavior.
- Feedback-triggered online learning, live model-weight updates or automatic RuleSet publication.
- Any update or deletion of historical MatchSnapshot, EligibilityResult, ranking or RuleSet rows.
- LLM final review, LLM final qualification decisions or opaque agent adjudication.
- Arbitrary evidence URLs, file upload, email ingestion, telephone-record storage or new source
  collection.
- General-purpose operations dashboard, analytics dashboard, bulk adjudication, user search or
  workflow-builder functionality.
- Production identity, public reviewer authentication, commercial behavior, payment, deployment,
  merge, ready-for-review, release or contract `STABLE` promotion.
- Real participant recruitment or collection of real participant data without separate user
  authorization.

## 4. Why v0.6 is necessary

The earlier contract families cannot express the Phase 7 boundary without being modified:

- v0.1 contains only an early proposed FeedbackEvent outline; it was not implemented as a complete
  review, label and validation workflow.
- v0.5 defines UserState, ranking and action facts but has no feedback-purpose consent, reviewer
  principal, review queue, assessment, adjudication, label, dual-track validation or release-gate
  contract.
- Phase 7 data crosses persistence, API, Web and evaluation boundaries and therefore needs a
  versioned, exportable contract rather than internal unversioned dictionaries.

Phase 7 will add `backend/src/deepaha/contracts/phase7.py`, a `v0.6.0` schema directory and one
strict synthetic example. It will not modify any committed byte under `contracts/schemas/v0.1.0`
through `v0.5.0`, and it will keep all existing Python imports available.

The v0.6 contract starts `PROPOSED`. Engineering evidence may advance it only to `IMPLEMENTED`.
Only a separate `QUALIFIED` Release Qualification could support a later `STABLE` decision.

## 5. Identity and purpose authorization

### 5.1 User principal

Personal feedback routes reuse the Phase 6 server-derived `Principal`. A request body or path never
accepts an authoritative `user_id`.

For a submission, the service must prove all of the following in one database transaction:

1. the authenticated user owns the referenced PersonalRankingSnapshot;
2. the referenced MatchSnapshot is an item in that exact ranking snapshot;
3. the MatchSnapshot's Opportunity ID/version equals the route opportunity and current submission
   command;
4. the ranking binds the referenced UserStateSnapshot and qualification profile;
5. the current UserState still permits the purpose required by the claim;
6. the submission contains the exact Phase 7 feedback consent version and scope.

Claim-to-existing-purpose mapping is fixed:

| Claim kind | Required current v0.5 purpose |
| --- | --- |
| `ELIGIBILITY_CORRECTION` | `ELIGIBILITY` |
| `OPPORTUNITY_FACT_CORRECTION` | `ELIGIBILITY` |
| `EXPLANATION_UNCLEAR` | `ELIGIBILITY` |
| `RANKING_IRRELEVANT` | `PERSONAL_RANKING` |

Every accepted command additionally declares:

```text
consent_version = phase7-feedback-consent-v1
consent_scope = FEEDBACK_REVIEW_AND_VALIDATION
```

The scope authorizes only governed review and offline validation. It does not authorize marketing,
commercial sharing, production training or an online rule update.

### 5.2 Reviewer principal

Phase 7 adds a separate fixture-only `ReviewerPrincipal` and reviewer-session digest table. A
reviewer credential is not a PersonalUser credential and cannot call `/api/v1/me` as a user.

Reviewer authentication:

- defaults to disabled;
- is permitted only in `development` and `test`;
- stores only a SHA-256 token digest;
- validates active status, expiry and revocation;
- derives roles and allowed purposes server-side.

Minimum controlled roles are:

| Role | Allowed operation |
| --- | --- |
| `FEEDBACK_REVIEWER` | read assigned/unassigned queue cases and append an assessment |
| `FEEDBACK_ADJUDICATOR` | append a confirmed/rejected/needs-evidence/conflict decision |
| `LABEL_CURATOR` | create a label asset from a confirmed adjudication |
| `VALIDATION_REVIEWER` | create the single improvement, offline, shadow and Gate records |

The fixture may assign several roles to one synthetic reviewer to exercise the vertical slice. The
service still checks the exact role and purpose for each operation.

### 5.3 Existence privacy

- An unknown event and another user's event return the same generic private `404` to user routes.
- A missing review case and a case outside the reviewer purpose return the same generic review
  resource result after authentication/role checks.
- Responses never expose owner IDs, auth-session digests, reviewer-session digests or unrelated
  profile data.
- User status responses omit reviewer identity, internal confidence and internal risk notes.
- Personal and reviewer success/error responses use `Cache-Control: private, no-store`.

## 6. Contract and persistence model

### 6.1 Immutable FeedbackEvent

`FeedbackEventSchemaV06` and `feedback_events` contain only the submitted fact:

- `feedback_event_id`;
- server-derived owner relationship;
- `ranking_snapshot_id`;
- `match_snapshot_id`;
- `opportunity_id` and `opportunity_version`;
- `user_state_snapshot_id` and `user_state_version`;
- `event_type = STRUCTURED_CORRECTION | EXPLICIT_EVALUATION`;
- one controlled claim kind;
- bounded `user_statement` and structured reason code;
- consent version and scope;
- contract version, canonical input SHA-256 and `created_at`.

No review status, reviewer, assessed confidence, adjudication, resulting label or release version is
stored in the raw event. The row is insert-only. PostgreSQL blocks `UPDATE` and `DELETE`, and tests
exercise both failures.

The command accepts no names, phone numbers, email addresses, government identifiers, free-form
biography, uploaded documents or arbitrary JSON keys. The optional statement is trimmed and
bounded to 500 characters; the UI warns users not to include sensitive personal information.

### 6.2 Evidence supplement

`FeedbackEvidenceLinkSchemaV06` and `feedback_evidence_links` are append-only and separately bind:

- the FeedbackEvent;
- an existing EvidenceRef and its Document;
- `SUPPORTS` or `CONTRADICTS` relation;
- actor kind (`USER` or `REVIEWER`) and server-derived actor identity;
- bounded structured note, canonical digest and creation time.

The service accepts an EvidenceRef only when it is the OpportunityVersion's source EvidenceRef or
appears in that exact version's governed field evidence. Phase 7 does not ingest a new URL or source
artifact through this API.

### 6.3 Versioned Review Queue

`FeedbackReviewCaseSnapshotSchemaV06` and `feedback_review_case_snapshots` form an append-only
stream keyed by `review_case_id` and positive version. Queue reads select the latest version.

Allowed statuses are:

- `RECEIVED`;
- `NEEDS_EVIDENCE`;
- `CONFLICT`;
- `CONFIRMED`;
- `REJECTED`.

The initial `RECEIVED` snapshot is created atomically with the raw event. Each later transition
creates another snapshot. Queue priority, due time, assignment and transition reason live in this
projection, not in FeedbackEvent. SLA is limited to deterministic priority/due-time display and
overdue calculation; no reminder or notification is added.

### 6.4 Confidence assessment

`FeedbackConfidenceAssessmentSchemaV06` and `feedback_confidence_assessments` contain a reviewer's
append-only assessment:

- evidence completeness;
- controlled confidence band `LOW | MEDIUM | HIGH`;
- risk level `NORMAL | HIGH_IMPACT`;
- conflict flag;
- referenced EvidenceRef IDs;
- bounded rationale;
- reviewer principal, purpose and timestamp.

Confidence is not a model probability, eligibility percentage or user-facing qualification score.
It cannot change the raw event or historical match.

### 6.5 Human adjudication

`FeedbackAdjudicationSchemaV06` and `feedback_adjudications` record one append-only decision per
case version. In a real environment the authenticated reviewer principal must represent a human
reviewer; the engineering fixture uses an explicitly synthetic reviewer principal and preserves
that provenance rather than claiming a real human review:

- `NEEDS_EVIDENCE`;
- `CONFLICT`;
- `CONFIRMED`;
- `REJECTED`.

`CONFIRMED` requires at least one linked governed EvidenceRef and a prior assessment. `REJECTED`
requires a bounded reason. The adjudicator is always a server-authenticated reviewer principal;
there is no model/provider field and no LLM decision path.

An adjudication creates a new ReviewCaseSnapshot but never edits FeedbackEvent, RuleSet,
EligibilityResult, MatchSnapshot, OpportunityVersion or ranking data.

### 6.6 Approved label asset

`ApprovedFeedbackLabelSchemaV06` and `approved_feedback_labels` are separate immutable assets.
A label may be created only when:

- the latest case status is `CONFIRMED`;
- an authenticated reviewer-principal adjudication exists and its real/synthetic provenance is
  retained;
- its supporting EvidenceRefs remain bound to the original OpportunityVersion;
- the curator has `LABEL_CURATOR` authority;
- the source fixture/participant evidence class is preserved.

The label records the original feedback, adjudication, match/version bindings, claim kind, approved
target value or expected interpretation, evidence IDs, provenance class and content SHA-256. It is
an offline asset, not an online RuleSet row.

### 6.7 One improvement direction

`ImprovementCandidateSchemaV06` and `feedback_improvement_candidates` declare exactly one change
direction for a validation cycle:

- `EXPLANATION_CLARITY`;
- `OPPORTUNITY_FACT_QUALITY`;
- `ELIGIBILITY_RULE_CANDIDATE`;
- `RANKING_POLICY_CANDIDATE`.

Each candidate contains one component, one versioned input manifest, one bounded change statement
and one candidate digest. A database uniqueness rule allows at most one selected candidate per
Phase 7 validation cycle. It cannot contain a bundle of rule, ranking and explanation changes.

The fixed engineering fixture selects `EXPLANATION_CLARITY` only as synthetic workflow input. That
selection is not a real product decision.

### 6.8 Offline, shadow and release-gate separation

The following records are distinct and append-only:

- `OfflineEvaluationCandidateSchemaV06`: binds one improvement candidate, one dataset manifest,
  baseline/candidate component versions and offline result digest;
- `ShadowTestCandidateSchemaV06`: can be created only after an acceptable offline record and binds
  a separate comparison digest; it has no production traffic or write path;
- `ReleaseGateDecisionSchemaV06`: consumes the candidate, offline result, shadow result and the two
  validation-track states.

Allowed release decisions are:

- `HOLD_MISSING_HUMAN_EVIDENCE`;
- `HOLD_ENGINEERING_FAILURE`;
- `REJECTED`;
- `CANDIDATE_ACCEPTED_FOR_FUTURE_IMPLEMENTATION`.

The last value authorizes only a later versioned implementation candidate; it does not deploy or
modify a live component. Database/service rules prohibit it when either validation track is
missing, failed or synthetic-only. With Phase 7's fixed fixtures, the only valid final state is
`HOLD_MISSING_HUMAN_EVIDENCE`.

## 7. Dual-track validation

### 7.1 Simulation track

The simulation track consumes only versioned synthetic profile/Golden manifests. It reports
integer engineering measures such as:

- case count;
- expected-status reproduction count;
- unexpected `INELIGIBLE` count and exact case IDs;
- replay mismatch count;
- controlled candidate-versus-baseline difference count.

Its evidence label is `SYNTHETIC_SIMULATION_ONLY`. It must not contain retention, willingness to
pay, participant trust, completion or real action claims.

### 7.2 Human-participant track

The human track has a separate dataset identity and strict evidence class
`CONSENTED_HUMAN_PARTICIPANT`. Its allowed measures are counts tied to the governed participant
protocol:

- participant count;
- structured feedback count;
- comprehension review count;
- cognitive-load review count;
- high-intent action count;
- withdrawals/exclusions.

It does not reuse simulation profile IDs, simulation truth, simulated clicks or synthetic reviewer
events. A synthetic flag or fixture manifest is rejected from this track. No human-track run will
be created in Phase 7 engineering verification; its status remains `NOT_STARTED`.

### 7.3 Synthetic feedback workflow fixture

Phase 7 adds a small deterministic CC0 fixture whose manifest declares:

```text
synthetic = true
contains_personal_data = false
business_truth = false
release_qualification_eligible = false
evidence_class = SYNTHETIC_FEEDBACK_WORKFLOW_ONLY
```

It exercises user isolation, review, adjudication, label creation, one selected improvement,
offline/shadow separation and a mandatory hold decision. It never enters the human-participant
dataset and its pass count is never described as a user metric.

## 8. Services and transactions

### 8.1 FeedbackService

Responsibilities:

- validate owner, purpose and exact historical version binding;
- canonicalize/hash the command;
- provide owner-scoped idempotency using a Phase 7-specific idempotency table;
- create FeedbackEvent, initial evidence links and ReviewCaseSnapshot atomically;
- append a later governed EvidenceRef supplement;
- return owner-safe status projections.

It has no dependency on RuleSet write services or ranking mutation methods.

### 8.2 ReviewService

Responsibilities:

- authenticate and authorize the ReviewerPrincipal;
- load only the minimum case, match and evidence facts needed for review;
- append assessments and adjudications;
- append the next review-case snapshot;
- create an approved label only through an explicit curator action.

It does not update raw feedback or online decision rows.

### 8.3 ValidationService

Responsibilities:

- select one improvement direction per cycle;
- create offline and shadow candidate records in order;
- validate simulation/human evidence classes and metric shapes;
- issue a non-deploying ReleaseGateDecision;
- prove that synthetic-only evidence forces a hold.

The service uses deterministic local inputs only. No model, network call or production traffic is
needed for normal tests.

### 8.4 Idempotency and failure atomicity

All user/reviewer writes require exactly one bounded `Idempotency-Key`. Phase 7 stores only its
SHA-256 digest. Replaying the same operation and request returns the same resource; reusing a key
with different bytes returns a private `409`. Any failure rolls back the complete write set.

## 9. API design

### 9.1 Personal API

Under `/api/v1/me`:

| Method and path | Purpose |
| --- | --- |
| `POST /opportunities/{public_id}/feedback` | submit one structured event against an exact ranking/match |
| `GET /feedback` | list the caller's own feedback status summaries |
| `GET /feedback/{feedback_event_id}` | load one owner-safe status and evidence summary |
| `POST /feedback/{feedback_event_id}/evidence` | append an existing governed EvidenceRef |

Invalid shape is generic `400`; authentication failure is generic `401`; idempotency conflict is
generic `409`; unknown/other-owner is identical `404`; database failure is non-sensitive `503`.

### 9.2 Reviewer API

Under `/api/v1/review/feedback`:

| Method and path | Required role |
| --- | --- |
| `GET /` | `FEEDBACK_REVIEWER` |
| `GET /{review_case_id}` | `FEEDBACK_REVIEWER` |
| `POST /{review_case_id}/assessments` | `FEEDBACK_REVIEWER` |
| `POST /{review_case_id}/adjudications` | `FEEDBACK_ADJUDICATOR` |
| `POST /{review_case_id}/labels` | `LABEL_CURATOR` |

Validation candidate operations remain an internal service/fixture workflow in Phase 7; they are
not expanded into a general administrative API.

## 10. Minimal Web experience

### 10.1 User correction and status

The personal opportunity detail gains a text button/link, `纠正这条判断`, leading to a separate
page. The page contains:

- the opportunity title and exact match/version context;
- one controlled correction type;
- one controlled structured reason;
- an optional 500-character statement with a sensitive-data warning;
- checkboxes for the already displayed official EvidenceRefs;
- explicit feedback consent text;
- loading, validation, success and failure feedback.

After submission the user sees a status page with public language for `已接收`, `需要补充证据`,
`存在证据冲突`, `已确认` or `未采纳`. It never shows internal confidence, risk score or reviewer
identity.

### 10.2 Controlled reviewer interface

The internal reviewer route provides only:

- a finite queue list sorted by priority, due time and stable ID;
- a case page with original statement, exact MatchSnapshot/version, existing official evidence,
  supplements and current queue history;
- one assessment form;
- one adjudication form;
- one explicit label-creation action after confirmation.

There are no charts, bulk actions, arbitrary user lookup, source editing, rule editing, model
controls or deployment controls. The route is absent from normal public/user navigation.

### 10.3 UI quality rules

- Reuse the existing Phase 5/6 typography, trusted blue/orange tokens and content-first layout.
- Do not generate a new logo, palette, dashboard theme or decorative animation.
- Preserve semantic headings, native form controls, visible labels and predictable back links.
- Announce validation/submission errors with `role=alert` or an equivalent live region.
- Keep keyboard order equal to visual order, focus visible, mobile controls at least 44 px and body
  text at least 16 px.
- Verify 375x812 and 1440x900 without horizontal overflow.
- Fetch initial data in Server Components and perform mutations through Server Actions; credentials
  remain in HttpOnly fixture cookies and server-only modules.

## 11. Migration and database safety

Phase 7 adds migration `20260822_0007_phase7_feedback_review_validation.py` after `0006`.

The migration may:

- add Phase 7 tables, indexes, restrictive foreign keys and immutable-row triggers;
- add a supporting uniqueness constraint to an existing Phase 6 table only if required for an
  exact owner/match composite foreign key and proven compatible with all existing rows.

It may not:

- rewrite or delete an existing Phase 1–6 row;
- change historical JSON Schema bytes;
- replace a v0.5 value or import path;
- relax an existing eligibility/evidence constraint.

An empty `0007` downgrade/re-upgrade must work. A populated downgrade must fail before deleting any
FeedbackEvent, evidence link, review history, adjudication, label or validation record.

## 12. Test strategy

Every implementation task follows RED -> minimum implementation -> focused GREEN -> risk-matched
regression -> exact staging -> independent commit -> ordinary push.

### 12.1 Contract tests

- deterministic v0.6 renderer/example parity;
- v0.1–v0.5 schema bytes and imports unchanged;
- strict enums, bounds, version pairs and synthetic/human evidence-class rejection;
- human metrics cannot be constructed from a synthetic fixture;
- a release acceptance cannot be constructed without both qualifying tracks.

### 12.2 Persistence tests

- exact owner/ranking/match/opportunity/user-state foreign relationships;
- raw event/evidence/assessment/adjudication/label/validation immutability;
- review snapshot stream version continuity;
- restrictive deletion and populated-downgrade refusal;
- migration upgrade, empty downgrade/re-upgrade and `alembic check`.

### 12.3 Authorization and privacy tests

- no body/path `user_id` authority;
- missing, malformed, expired and revoked user/reviewer credentials;
- user token rejected from reviewer routes and reviewer token rejected from personal routes;
- role/purpose denial for each reviewer operation;
- other-owner and unknown user resources produce identical responses;
- no tokens, digests, owner IDs, reviewer identity, SQL or internal confidence in user errors/logs.

### 12.4 Governance tests

- FeedbackEvent and initial queue record commit atomically and idempotently;
- only EvidenceRefs governed for the exact OpportunityVersion can be linked;
- confirmed adjudication requires assessment and evidence;
- label creation requires confirmed human adjudication;
- feedback does not change pre/post RuleSet, MatchSnapshot, EligibilityResult or ranking digests and
  row counts;
- at most one improvement direction can be selected;
- offline must precede shadow, and shadow must precede Gate decision;
- synthetic-only evidence produces `HOLD_MISSING_HUMAN_EVIDENCE`;
- no LLM/provider/model field or runtime call participates in adjudication.

### 12.5 Web and browser tests

- user correction form, evidence selection, consent and status states;
- reviewer queue/case/assessment/adjudication/label flow;
- loading, empty, invalid, unauthorized, conflict, dependency-failure and recovery states;
- keyboard navigation, visible focus, error announcement, mobile touch targets and no overflow;
- no percentage/confidence-as-eligibility claim, reviewer disclosure, token, Phase 8 control or
  production-release claim.

## 13. Fixed fixtures and evidence language

The fixture contains fictional opaque users/reviewers, existing Phase 5/6 synthetic opportunities,
exact MatchSnapshots and a small set of corrections/evidence links. IDs and timestamps are stable;
runtime credentials are generated and only digests enter PostgreSQL.

The manifest includes exact filenames, SHA-256, byte lengths, record counts, generator version,
scenario clock, `CC0-1.0`, synthetic/privacy/business-truth/qualification flags and an explicit
purpose statement.

Allowed evidence wording:

- `synthetic feedback workflow passed`;
- `simulation replay counts`;
- `real participants = 0`;
- `human track = NOT_STARTED`;
- `Release Qualification = NOT_STARTED`.

Prohibited wording includes synthetic pass rates presented as participant trust, correction
accuracy, retention, willingness to pay, real action, production safety or qualification.

## 14. Isolation, verifier and CI

Phase 7 uses only:

- Compose project names matching `deepaha-phase7-*`;
- `infra/compose.phase7.yaml`;
- PostgreSQL `127.0.0.1:55437`;
- Moto `127.0.0.1:55005`;
- temporary application ports selected and ownership-checked for browser QA.

The verifier must reject occupied Phase 7 ports unless owned by its exact project and must clean
only that project in `finally`. It must not reference, connect to, start, stop or clean Phase 2–6
projects or ports.

CI adds `phase7-feedback-review` while preserving:

- `backend-quality`;
- `web-quality`;
- `integration`;
- `phase3-resolution`;
- `phase4-eligibility`;
- `phase5-public-trust`;
- `phase6-profile-action`.

The Phase 7 job runs offline contracts, authorization/governance tests, PostgreSQL integration,
migration cycle, fixture verification and relevant Web tests. It performs no live-source, model or
real-participant call.

## 15. Engineering Gate package

`docs/gates/phase-7/` will contain at least:

- `README.md`;
- `acceptance-results.md`;
- `test-summary.md`;
- `browser-verification.md`;
- `code-review.md`;
- `security-and-compliance.md`;
- `dual-track-validation.md`;
- `operations.md`;
- `deferred-decisions.md`.

Before closing the Engineering Gate, the final candidate review must inspect the complete Phase 7
diff and record scope, authorization, existence privacy, consent/purpose, immutable history,
evidence provenance, migration, license, secret, artifact, browser, accessibility and inherited
regression results.

Engineering Gate closure may set only:

- Implementation `IMPLEMENTED`;
- Engineering Gate `CLOSED`;
- Release Qualification `NOT_STARTED`;
- v0.6 Contract Maturity `IMPLEMENTED`.

It may not claim real participant validation, a released improvement or `STABLE`.

## 16. Delivery and Git boundary

- Do not rebase or force-push.
- Do not modify the Phase 6 branch or existing Phase 2–6 worktrees/runtimes.
- Use exact-path staging, independent task commits and ordinary push.
- Create a stacked draft PR with base `codex/phase-6-profile-match-personal-action` and head
  `codex/phase-7-feedback-review-validation`.
- Keep the PR open, draft and unmerged.
- Wait for all required jobs on the final exact SHA to complete successfully.
- Record the final SHA, workflow run, every job conclusion and the synthetic/human evidence boundary
  in the PR body without creating a self-referential documentation commit loop.

## 17. Design success criteria

The design is realized only when executable evidence proves:

1. prior contracts remain byte/import compatible and v0.6 is no more than `IMPLEMENTED`;
2. raw feedback and all governance facts are immutable/versioned as designed;
3. user/reviewer identity, purpose, role, owner isolation and existence privacy fail closed;
4. every correction binds exact historical decision inputs and governed official evidence;
5. no feedback path mutates online rules, historical decisions or ranking;
6. only confirmed authenticated reviewer adjudication can create a label asset, and synthetic
   reviewer provenance can never be reported as real human evidence;
7. one and only one improvement direction is selected per validation cycle;
8. simulation and human tracks cannot share datasets, metrics or evidence language;
9. synthetic-only engineering evidence forces the release gate to hold;
10. the minimal user/reviewer browser flow is usable and does not become an operations platform;
11. isolated local verification and final exact-SHA remote CI pass;
12. the four axes and all deferred real work remain truthful.

## 18. Deferred decisions

- Real design-partner recruitment, consent administration and human-track evidence collection.
- General privacy access/export/deletion and consent-withdrawal lifecycle tied to production
  identity and a reviewed retention policy.
- New external evidence ingestion or source collection initiated from feedback.
- Implementing the selected improvement in an online parser, rule, explanation or ranker.
- Production reviewer identity, separation-of-duty staffing, monitoring and incident response.
- Phase 8 notifications and all production/commercial capabilities.

These deferrals do not weaken Phase 7's immutable audit, authorization or no-online-update rules.
They block Release Qualification and production use, not the bounded Engineering Gate.
