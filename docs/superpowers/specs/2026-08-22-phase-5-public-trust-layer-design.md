# DeepAha Phase 5 Public Trust Layer Design

> Date: 2026-08-22
>
> Design status: `APPROVED FOR IMPLEMENTATION`（用户已在任务中授权设计完成后持续执行，
> 无需常规人工 review checkpoint）
>
> Exact upstream: Phase 4 docs-only head
> `8840fe33bd3946a10a5b4448a59f2bf4d7622c3d`
>
> Startup axes: Implementation `NOT_STARTED`; Engineering Gate `OPEN`; Release Qualification
> `NOT_STARTED`; Phase 5 Public API Contract Maturity `PROPOSED`

> Closure evidence (2026-08-22): Implementation `IMPLEMENTED`; Engineering Gate `CLOSED` on exact
> candidate SHA `492c8b34562dca59c2a66d6e4d3ea769345803ca` and successful GitHub Actions run
> `32549701629`; Release Qualification `NOT_STARTED`; Phase 5 Public API Contract Maturity
> `IMPLEMENTED` and not `STABLE`.

## 1. Purpose and bounded outcome

Phase 5 delivers one read-only vertical slice from the governed Opportunity record to a public,
responsive Web/PWA experience. A visitor can deterministically search and inspect a finite catalog,
verify the current facts against official links and explicit `EvidenceRef` locators, and review the
Opportunity version/event history.

This phase improves the `可信发现` part of the product loop. It does not collect a user profile,
calculate eligibility, rank personally, create an action plan, or expose any Phase 6 user flow.

The minimum successful outcome is:

1. only explicitly approved catalog entries can appear publicly;
2. every visible item has all required public trust fields and a current governed version;
3. list and detail responses are deterministic, read-only and reproducible;
4. the Web experience is usable at mobile and desktop widths and with keyboard-only navigation;
5. fixture data is visibly identified as license-safe synthetic evidence and cannot be counted as
   200 real Gold Opportunities;
6. local, browser and exact-SHA remote CI evidence supports Engineering Gate closure without
   starting Release Qualification.

## 2. Decision sources and inherited invariants

This design is derived from, in priority order, the current task, `AGENTS.md`, Blueprint v1.2,
Phase 5 in the system roadmap, the v0.1-v0.4 contracts, and the Phase 1-4 Engineering Gate evidence.

The following inherited invariants remain unchanged:

- `Source -> RawArtifact -> Document -> Opportunity -> Version / Event -> RuleSet -> Match -> Action`.
- `Document != Opportunity`; the public page represents the stable Opportunity, not a copied page.
- original evidence is immutable; public projections do not overwrite source facts or history.
- stable `public_id`, versions, events and evidence relations remain the reproduction identity.
- qualification and recommendation remain separate. Phase 5 returns neither.
- no uncertain or model-derived fact is presented as a hard public fact without an evidence link.
- v0.1-v0.4 canonical Schema bytes and Python import paths remain byte/import compatible.
- Phase 4 remains Implementation `IMPLEMENTED`, Engineering Gate `CLOSED`, Release Qualification
  `NOT_STARTED`, v0.4 `IMPLEMENTED` and not `STABLE`.

## 3. Scope

### 3.1 In scope

- an additive public-catalog governance record tied to an exact Opportunity version;
- a read-only public list API and detail API;
- stable ID, title, type, jurisdiction/locations, issuer, status, published/deadline/verified times,
  official entry URL, attachments, key evidence and version/event history;
- bounded text search; explicit type, status and region filters; a finite sort enum; deterministic
  cursor pagination;
- a Next.js responsive public directory, detail page, loading/empty/error states and PWA manifest;
- an honest `判断我是否适合` boundary page that says Phase 6 is unavailable and performs no
  collection or computation;
- fixed synthetic/license-safe fixtures used only by tests and browser engineering QA;
- migration, verifier, CI job, browser evidence and Phase 5 Gate documentation.

### 3.2 Explicitly out of scope

- real profiles, eligibility output, personal ranking, action desk, personal APIs or user accounts;
- LLM/Model Gateway, semantic execution, Redis/Valkey/Celery, pgvector, source-side Playwright,
  Docling/OCR, notifications, feedback, commercial placement, production cloud or release;
- Phase 2 live observation changes or access to Phase 2/3/4 fixed local ports;
- unbounded aggregation, national expansion, fabricated real Gold data, fake matching percentages,
  any `STABLE` promotion, PR merge or release.

## 4. Alternatives considered

### 4.1 Static fixture-only catalog

A static JSON catalog would be small, but it would bypass the existing Opportunity/Version/Event/
Evidence persistence and make it impossible to prove that only governed records are visible. It is
rejected as the product path; JSON remains acceptable only as a deterministic test fixture input.

### 4.2 Publish every `Opportunity.publication_status = PUBLISHED`

The existing publication status is necessary but not sufficient: it does not identify the Gold
candidate collection, its exact reviewed version, the use basis, or the last verification time.
Publishing every `PUBLISHED` row could turn Phase 5 into an uncontrolled feed. This is rejected.

### 4.3 Add a v0.5 domain-contract family

Phase 5 needs an application projection and a catalog allowlist, not a new domain truth object.
Adding v0.5 would duplicate stable v0.1-v0.4 entities and create unnecessary compatibility work.
The public HTTP response models will therefore be versioned as the Phase 5 Public API contract,
while canonical domain contracts remain unchanged.

### 4.4 Selected approach: governed allowlist plus derived projection

Add one narrowly scoped `public_catalog_entries` table. It records the exact approved Opportunity
version and governance metadata; all public facts are still read from the existing Opportunity,
OpportunityVersion, OpportunityEvent, EvidenceRef, Document, RawArtifact and Source records.
This is the smallest enforceable boundary between an internal Opportunity and a public catalog item.

## 5. Persistence and governance model

### 5.1 `public_catalog_entries`

One row governs one currently visible Opportunity:

| Field | Meaning / constraint |
|---|---|
| `opportunity_id` | primary key and restrictive FK to Opportunity |
| `opportunity_version` | restrictive composite FK to the exact OpportunityVersion |
| `collection_kind` | `REAL_GOLD` or `LICENSE_SAFE_FIXTURE` only |
| `dataset_id` / `dataset_version` | non-empty, versioned collection identity |
| `content_use_basis` | existing controlled values: `OPEN_LICENSE`, `OFFICIAL_PUBLIC_ACCESS`, `LINK_ONLY` |
| `reviewed_by` | non-empty governance actor; not exposed publicly |
| `approved_at` | approval audit instant |
| `last_verified_at` | DeepAha catalog verification instant, not an official publication time |

The database enforces positive version, controlled enums, non-empty governance strings and
`last_verified_at >= approved_at`. Foreign keys use `ON DELETE RESTRICT`. Migration `0005` is
additive and does not update existing rows. Downgrade is allowed only while this table is empty;
otherwise it refuses rather than deleting publication governance evidence.

### 5.2 Visibility predicate

An item is public only when every condition holds:

- the Opportunity has `publication_status = PUBLISHED`;
- `current_version` equals the allowlisted `opportunity_version`;
- that exact version exists and is not rejected;
- all required snapshot fields validate into the inherited v0.3/v0.4 Opportunity snapshot model;
- title/type/issuer/status, published time, deadline, official application URL, verification time,
  at least one key field evidence reference and official source URL are present;
- official URLs are `http`/`https`, contain no user information and are derived from stored facts;
- collection kind is one of the two governed values.

Incomplete or stale-version rows are omitted from the list and return public `404` by stable ID.
They are not partially rendered with invented fallbacks.

### 5.3 Synthetic evidence boundary

The repository may contain a small, fixed `LICENSE_SAFE_FIXTURE` dataset for tests. Its manifest
states that it is generated, non-personal and not business truth. API responses include a public
`data_label`, and the Web renders an explicit fixture banner. No fixture count is converted into
coverage, accuracy, public-field qualification or Release Qualification evidence.

## 6. Public API contract

### 6.1 Endpoints

- `GET /api/v1/public/opportunities`
- `GET /api/v1/public/opportunities/{public_id}`

The router registers only `GET` and implicit `HEAD` behavior. There are no write endpoints under
the public prefix. Each request uses a transaction configured `READ ONLY` on PostgreSQL before any
query. Service methods contain only SQLAlchemy `SELECT` statements.

### 6.2 List query

Supported query parameters are deliberately finite:

- `q`: trimmed, 1-100 characters; literal case-insensitive search across stable ID, title and issuer;
- `type`: one inherited Opportunity type;
- `status`: one inherited public status;
- `region`: trimmed, 1-80 characters; literal match against jurisdiction or snapshot locations;
- `sort`: `PUBLISHED_DESC` or `DEADLINE_ASC`;
- `cursor`: opaque URL-safe token bound to the active sort tuple;
- `limit`: integer 1-50, default 20.

`PUBLISHED_DESC` orders by `published_at DESC, public_id ASC`. `DEADLINE_ASC` orders by deadline
`ASC, public_id ASC`; visibility requires a deadline, so null ordering is not ambiguous. The cursor
contains only the sort key and stable ID, is schema-validated, and invalid values return a stable
`400` problem response. Search escapes SQL wildcard characters so user input is literal.

The list response contains `items`, `next_cursor`, `count`, `data_labels` and `reproduced_at`.
`reproduced_at` reports the greatest catalog `last_verified_at` among the returned rows, not the
request clock, so identical data and query produce identical response content.

### 6.3 Detail response

The detail response contains:

- all list-card fields;
- official application URL and attachment URLs;
- current version number;
- key field evidence entries with field path, EvidenceRef ID, Document ID, locator kind/payload,
  evidence authority/precedence and an official source URL;
- events ordered by `to_version ASC, detected_at ASC, event_id ASC`, including event type, version
  transition, changed fields, detected time and official evidence link;
- `personalization_availability = PHASE_6_NOT_IMPLEMENTED`.

No raw object-storage URI, parser text URI, review actor, internal review note, profile, rule result,
eligibility result, model confidence or matching percentage is returned.

### 6.4 Error format and caching

Invalid query/cursor uses `400`; an unknown or non-visible stable ID uses `404`; an unexpected
dependency failure uses a non-sensitive `503`. Responses use an RFC 9457-style
`application/problem+json` shape with `type`, `title`, `status`, `detail` and request path only.
Stack traces, SQL and secrets are never exposed.

Public GET responses may return `Cache-Control: public, max-age=60, stale-while-revalidate=300`.
Caching never changes sort semantics or replaces evidence/version identity.

## 7. Web/PWA experience

### 7.1 Information architecture

- `/`: concise DeepAha public-trust introduction and a primary link to the opportunity catalog;
- `/opportunities`: search, finite filters, deterministic results, empty state and pagination;
- `/opportunities/[publicId]`: trusted fields, official links, evidence locators and change timeline;
- `/opportunities/[publicId]/fit-check`: static Phase 6 boundary message with a return link.

Next.js server components call the read-only API. Route-level `loading.tsx` and `error.tsx` provide
clear states; errors do not silently turn into empty results. Search and filters use ordinary GET
form fields, making the URL reproducible and keyboard-native.

### 7.2 PWA shell

Phase 5 adds a Web App Manifest with name, short name, start URL, standalone display and chosen
theme/background colors. It does not claim offline data synchronization or notification support.
No raw `设计/logo.png` bytes are shipped because that asset contains white background/watermark.
The header uses the approved `DeepAha` casing and exact tagline as a text wordmark; no replacement
logo is invented.

### 7.3 UI constraints

The `ui-ux-pro-max` review identifies an accessible public directory pattern. Phase 5 adopts only
the applicable constraints:

- semantic landmarks, one page `h1`, labeled controls and a skip link;
- at least 16 px body text, 44 px touch targets and visible 3 px focus rings;
- a high-contrast navy/blue trust hierarchy, with orange reserved for `Aha`/important discovery;
- tokens are selected and contrast-checked for Phase 5; none are sampled from reference posters;
- no purple AI gradient, decorative motion, fake counters, icon-only unlabeled controls or hover-only
  information;
- `prefers-reduced-motion` is respected;
- content remains usable at 375, 768, 1024 and 1440 px widths without horizontal overflow.

Automated Web tests cover semantic content and negative Phase 6 assertions. A real-browser pass
covers mobile/desktop screenshots, keyboard order, loading/error/empty paths, official-link target
attributes, focus visibility and absence of horizontal overflow.

## 8. Failure modes and controls

| Failure mode | Control |
|---|---|
| Internal or incomplete Opportunity becomes public | allowlist + exact current-version + completeness predicate |
| A changed Opportunity shows stale facts | allowlist is version-bound; version mismatch hides the row until re-review |
| Public fact cannot reach evidence | mandatory field evidence and official URL; detail tests validate every hard field |
| Search changes ordering between requests | finite sort enum, stable tie-breaker, cursor bound to sort tuple |
| SQL wildcard or oversized input broadens query | escaped literal search and strict length/limit validation |
| API mutates publication facts | GET-only router, PostgreSQL read-only transaction and write-negative tests |
| Fixture looks like real Gold | `LICENSE_SAFE_FIXTURE` label in DB, API, UI and evidence docs |
| Public page implies personal eligibility | no eligibility fields/percentages; static `PHASE_6_NOT_IMPLEMENTED` boundary |
| Error leaks SQL or secret | stable problem response; tests assert sensitive strings absent |
| UI hides status from assistive tech | semantic HTML, labeled controls, live-safe text states, browser keyboard checks |
| PWA implies unavailable offline/notification features | manifest-only shell; no service worker or notification claim |

## 9. Test and verification strategy

Every implementation task follows RED -> minimum GREEN -> directed verification -> risk-matched
regression -> exact-path staging -> commit -> ordinary push.

### 9.1 Backend tests

- migration/ORM metadata, additive upgrade, empty downgrade/re-upgrade and populated refusal;
- catalog constraints, exact-version visibility and stale/incomplete exclusion;
- list fields, literal search, filters, both sorts, cursor pagination and invalid cursor;
- detail evidence/official link/history, unknown ID and no internal/private fields;
- GET-only route surface, read-only transaction and no qualification/matching percentage fields;
- v0.1-v0.4 canonical Schema byte and import compatibility via the existing contract suite.

### 9.2 Web tests

- home/catalog/detail/fit-check semantics;
- fixture banner, stable ID, dates/status, official/evidence/history links;
- loading, empty and error states;
- search/filter/pagination URLs and accessible names;
- negative assertions for personal eligibility, percentage, profile form and Phase 6 API behavior.

### 9.3 Isolated integration and browser verification

`scripts/verify-phase5.ps1` owns only a `deepaha-phase5-*` compose project using PostgreSQL 55435
and Moto 55003. It runs root quality, migration, Phase 5 integration/API tests, contract compatibility,
Web tests/build and Alembic drift, and removes only its exact project in `finally`.

Browser QA uses the same disposable Phase 5 environment plus a test-only synthetic seed path. It
does not perform source collection or access Phase 2/3/4 service ports.

## 10. Engineering Gate and Release Qualification

### 10.1 Engineering Gate closure

The Gate may become `CLOSED` only after all of the following are actual evidence:

- implementation, migration, Public API/Web and Phase 6 boundary exist;
- v0.1-v0.4 bytes/import paths remain compatible;
- local root and isolated Phase 5 verifier pass;
- browser mobile/desktop/accessibility checks pass on real rendered pages;
- scope, read-only security, secret/artifact/privacy/data-license and diff review pass;
- no unresolved Critical/Important code review finding remains;
- a stacked draft PR is open/draft/unmerged against the exact Phase 4 branch;
- every required job succeeds on the final exact Phase 5 SHA.

Only after these checks may the axes be updated to Implementation `IMPLEMENTED`, Engineering Gate
`CLOSED`, Phase 5 Public API Contract Maturity `IMPLEMENTED`. The contract cannot be `STABLE`.

### 10.2 Release Qualification

Release Qualification needs 200 real, permission-clear, verified Gold Opportunities in a real
candidate environment with 100% complete public trusted fields, reproducible official backlinks,
verification times and change histories. Fixed or synthetic fixtures, local browser screenshots and
CI cannot satisfy this. Unless real evidence is introduced by a separately governed process, Phase 5
Release Qualification remains `NOT_STARTED`.

Engineering Gate closure does not authorize merge, production release, expansion or contract
promotion. It also does not alter Phase 2 live observation.

## 11. Task-level commit sequence

1. `docs(phase5): design the public trust layer`
2. `docs(phase5): plan public trust implementation`
3. `feat(phase5): govern public catalog persistence`
4. `feat(phase5): expose read-only public opportunity API`
5. `feat(phase5): build responsive public trust web`
6. `test(phase5): add isolated verifier and CI gate`
7. `docs(phase5): close engineering gate evidence`

Each commit stages named files only and is pushed normally to
`codex/phase-5-public-trust-layer`. The PR remains draft/open/unmerged and is never rebased or
force-pushed.
