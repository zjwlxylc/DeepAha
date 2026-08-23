# P9-A Source Acquisition Platform Design

Status: `APPROVED DESIGN BASELINE`
Evidence date: 2026-08-23
Implementation status: `PLANNED`

## 1. Objective

DeepAha must add a reusable acquisition control plane above the existing Phase 2 evidence
foundation. The platform must acquire heterogeneous official sources through a small number of
policy-bound strategies, distinguish transport success from semantic content validity, preserve
raw evidence, block invalid content from the normal Document chain, support deterministic offline
replay, expose source health and integration cost, and degrade safely when automated access is not
appropriate.

The target is not to make one S02 page crawlable and is not to accumulate site-specific adapters.
The target is to prove across several materially different official sources that onboarding work
converges toward Source Recipe configuration and narrowly scoped discovery logic while the same
fetch, validation, persistence, replay and health capabilities are reused.

## 2. Inputs and precedence

This design reconciles:

1. `D:/DeepAha/文档/DeepAha_Source_Acquisition_Platform_Design_v1.0.md`;
2. `D:/DeepAha/文档/DeepAha_Source_Acquisition_Platform_Design_v1.0审查结果.md`;
3. the current repository implementation at local `main`/`origin/main`
   `cedce6f229dc341bf20107200b61e1f197b0d3d7`;
4. completed A0 commit `9d051044defaa2f41ad91f9aaf6e891742aaf8fa`;
5. the retained S02 Attempt 1 experiment
   `1cd1db777d6c85c180650efe733fe169aee218a1`;
6. the following approved corrections to the initial design.

The approved corrections are authoritative:

- persist semantic acquisition truth in a companion `AcquisitionEvaluation` table instead of
  expanding `capture_observations` with unrelated meaning;
- preserve a policy-permitted RawArtifact when content validation fails, but never advance that
  result through the normal Document transition;
- keep the existing `SourceTier` meaning and represent the source's role in a particular
  acquisition/evidence path separately;
- keep real response bytes outside Git in controlled storage; commit only a versioned manifest,
  hashes, locators and replay expectations;
- do not assume Browser acquisition is required; choose it only after an evidence-based
  feasibility check, and never use stealth, CAPTCHA bypass, credential bypass or access-control
  circumvention.

## 3. Current assets and architectural delta

The following current assets remain authoritative and are reused:

- versioned Source and SourceEndpoint registry;
- endpoint policy, robots decision, allowed-host, MIME, timeout, retry and rate-limit fields;
- `HttpxTransport` and the bounded, redirect-safe Phase 2 collector;
- CaptureObservation as transport truth;
- immutable RawArtifact storage, per-source SHA-256 deduplication and provenance;
- Document, ParseAttempt and EvidenceRef persistence;
- deterministic HTML, PDF and XLSX parsing and locator replay;
- Opportunity, version, rule, eligibility and downstream Phase 3-8 contracts.

The platform adds a thin control plane rather than a replacement core:

```text
Source Registry + Source Recipe
              |
              v
      Acquisition Orchestrator
              |
      policy-bound FetchRequest
              |
   Structured | Static HTTP | approved Browser | Manual
              |
              v
  CaptureObservation + RawArtifact
              |
              v
     AcquisitionEvaluation
              |
         VALID only
              |
              v
 Document -> Evidence -> Opportunity -> Rules
```

S02 Attempt 1 is `SELECTIVE_GENERALIZATION_ONLY`. Its challenge markers and genuinely
site-specific discovery/canonicalization may inform tests and a thin Recipe plugin. Its private
result, error, validation, deduplication and zero-discovery contracts do not become platform
interfaces.

## 4. Domain boundaries

### 4.1 Transport truth

`CaptureObservation` retains its current Phase 2 meaning:

- whether a transport attempt completed;
- request and resolved URL;
- HTTP status and validators;
- the RawArtifact produced or reused;
- stable transport failure code;
- collector and policy versions.

Its historical v0.2 schema and outcome constraints remain byte-compatible. A content challenge
must not be rewritten as a transport failure when HTTP transfer and RawArtifact persistence both
succeeded.

### 4.2 Semantic acquisition truth

`AcquisitionEvaluation` is additive and is linked to exactly one CaptureObservation and its
source/endpoint/artifact identity. A successful or not-modified observation in the P9-A flow must
have exactly one evaluation before any automatic Document transition.

Minimum fields:

- `acquisition_evaluation_id` UUIDv7 primary key;
- `observation_id` unique foreign key;
- composite source/endpoint/artifact foreign-key bindings;
- `strategy_used`;
- `validation_status`;
- nullable `challenge_type`;
- `redirect_chain` as an ordered JSON array of normalized public URLs;
- nullable non-negative `discovered_count`;
- `manual_intervention`;
- `validator_name`, `validator_version` and `metrics_schema_version`;
- bounded `validation_metrics` JSON object;
- `evaluated_at`.

Initial strategy values are `STRUCTURED`, `STATIC_HTTP`, `BROWSER`,
`OFFICIAL_ALTERNATIVE` and `MANUAL`. They describe acquisition mechanics, not authority.

Initial validation values are `VALID`, `CONTENT_CHALLENGE`, `CAPTCHA_REQUIRED`,
`AUTH_REQUIRED`, `ACCESS_DENIED`, `UNEXPECTED_CONTENT`, `ZERO_DISCOVERY_SUSPECT` and
`SELECTOR_DRIFT`. Transport failures remain CaptureObservation failures and do not fabricate an
evaluation without bytes.

The validation contract is fail closed:

- only `VALID` can advance automatically;
- challenge fields are present only for a challenge-related status;
- validation diagnostics are bounded, versioned and contain no credentials, cookies, tokens or
  full raw content;
- a validation failure never deletes or overwrites the RawArtifact.

### 4.3 Source authority and usage role

Existing Source tiers remain unchanged. Source Recipe and discovered relationships use a separate
`usage_role`:

- `PRIMARY_EVIDENCE`;
- `OFFICIAL_DISCOVERY`;
- `TRUSTED_LEAD`;
- `GENERAL_LEAD`.

Only `PRIMARY_EVIDENCE` content may support high-impact deterministic eligibility facts.
Discovery sources can create candidates and official link relationships but cannot silently
upgrade themselves into evidence sources.

## 5. Fetch contracts and implementations

`FetchRequest` is an immutable request value carrying source and endpoint IDs, requested URL,
strategy, allowed hosts, expected media types, timeout, attempt budget and policy version.
Dynamic detail or attachment URLs are allowed only when they remain inside the originating
endpoint's approved host and policy boundary.

`FetchResult` is an immutable transport value carrying request/final URL, ordered redirect chain,
strategy, fetch time, transport result, HTTP status, content type, bounded safe headers, body or
body reference, hash, fetcher version and stable diagnostics. Fetchers never create Opportunity,
Document, Evidence or eligibility facts.

`StaticHttpFetcher` adapts the existing `HttpxTransport` and collector protections. It does not
duplicate DNS/IP, redirect, MIME, size, retry, conditional-request or rate-limit rules.

`StructuredFetcher` may consume an approved public RSS, Atom, JSON, XML or stable official
interface. The same host, access, provenance, size, validation and RawArtifact rules apply.

`BrowserFetcher` is conditional. It may use standard Playwright Chromium only for normal public
rendering, with explicit resource/time limits and final DOM/network provenance. It must stop on
CAPTCHA, authentication or explicit access control. Stealth, fingerprint spoofing, token
reconstruction, proxy/cookie pools and bypass behavior are forbidden.

`Manual` is a governed fallback for approved official files or URLs. It preserves actor, policy,
hash and provenance and enters the same validation and evidence pipeline.

## 6. Content validation

`ContentValidator` is deterministic and runs before an automatic Document transition. It combines
generic transport-content checks with declarative Source Expectations.

Generic checks cover:

- empty/blank or implausibly short bodies;
- MIME mismatch;
- login, access-denied, cookie/JavaScript challenge and CAPTCHA markers;
- redirect to a non-approved host or login/error path;
- missing expected structural signals;
- malformed structured feeds;
- deterministic selector/list-count drift.

Source Expectations are configuration, not business extraction. They may contain bounded byte
limits, required/forbidden markers, selectors and minimum discovery counts. They cannot infer
Opportunity type, eligibility or missing facts.

The P9-A orchestrator is the normal acquisition-to-document entrypoint. It invokes parsing only
for `VALID` evaluations. Historical fixed-fixture and migration tests remain compatible and do not
retroactively require AcquisitionEvaluation rows.

## 7. Source Recipe and orchestration

A versioned Source Recipe identifies the source and endpoint, usage role, ordered Fetch Plan,
content expectations, discovery kind, pagination limits, detail/attachment URL policies and
health expectations. The schema forbids credentials and arbitrary executable code.

A thin source plugin is permitted only for discovery or canonicalization that cannot be expressed
declaratively. It must not implement transport, persistence, retry, rate limiting, validation,
replay, health or evidence storage.

The Acquisition Orchestrator:

1. loads an approved active endpoint and matching Recipe;
2. selects the next permitted strategy in the Fetch Plan;
3. enforces a total bounded plan budget;
4. executes the generic Fetcher;
5. persists CaptureObservation and RawArtifact through existing services;
6. validates and persists AcquisitionEvaluation;
7. emits discovered, canonicalized detail/attachment requests within policy limits;
8. advances only VALID artifacts to the existing Document service;
9. records stable stop/degrade reasons without attempting stronger bypass behavior.

Idempotent replay of the same request/result/validator versions produces the same evaluation and
does not duplicate RawArtifact, Document or Opportunity facts. Conflicting replay input fails
closed and is auditable.

## 8. Replay and real-source evidence

Tests are divided into three evidence classes:

- synthetic contract tests in default CI;
- real replay tests with network disabled;
- explicit low-frequency live source qualification.

Git stores a manifest containing source/endpoint IDs, public URL, fetch time, final URL, MIME,
byte size, SHA-256, object key, strategy/fetcher/validator/parser versions and expected outcomes.
Actual real HTML/PDF/XLSX bytes remain in policy-approved controlled object storage and are mounted
explicitly for replay. Absence of the controlled corpus skips or blocks real qualification; it
must never be replaced by a synthetic PASS claim.

Live collection obeys endpoint robots/content-use decisions, configured rate limits and bounded
request counts. It never accesses private data, credentials, login sessions or protected content.

## 9. Health, drift and integration cost

Health derives from persisted facts rather than HTTP status alone:

- accessibility;
- discovery;
- fetch integrity;
- parseability;
- evidenceability;
- drift.

The platform records per-run strategy usage, attempts, discovered/validated/parsed/attachment
counts, zero-discovery and drift flags, manual intervention and last validated success.

Per-source integration evidence records Recipe lines, source-specific production LOC, generic
strategy changes, core-schema changes, onboarding time, browser/manual ratios, run failures and
maintenance observations. These are engineering evidence, not product-value metrics.

## 10. Slice sequence

### A0 — deterministic baseline

Completed independently at `9d051044defaa2f41ad91f9aaf6e891742aaf8fa`. It is an ancestor of
this branch and is not mixed into an A1-only diff when reviewed.

### A1 — contracts, validation and companion persistence

Add Fetch contracts, deterministic ContentValidator, AcquisitionEvaluation contract/model,
additive migration, repository/service, StaticHttpFetcher adapter and the VALID-only P9-A document
transition. Do not add a new source or live traffic.

### A2 — Recipe and Orchestrator

Add the versioned Recipe schema/loader, usage role, Fetch Plan, bounded orchestration and thin
discovery interface. Prove with synthetic endpoints that dynamic URLs remain policy-bound and
that no source-specific code duplicates platform responsibilities.

### A5 — real strategy feasibility

Inspect S02 through approved, low-frequency L0/L1/L2-feasibility/L3 checks. Record current
official-source evidence, robots/use boundaries and exact stop reasons. Select a strategy without
implementing bypass behavior. Task-level authorization permits an evidence-based decision without
a per-Slice wait.

### A3 — conditional Browser or selected fallback

Implement BrowserFetcher only if A5 proves that standard public browser rendering is necessary,
permitted and useful. Otherwise implement the selected L0/L3 Recipe or governed L4 route and
record why Browser was unnecessary or inappropriate.

### A4 — health and integration cost

Add deterministic health/drift derivation and integration-cost evidence. It must consume common
observations/evaluations rather than source-specific counters.

### A6 — S02 real acceptance v2

Acquire 3-5 current official lifecycle samples when available, persist raw evidence, validate,
parse, resolve at least one complete Opportunity/Evidence path, prove exact dedup and offline
replay, and demonstrate that challenge/zero-discovery cannot silently pass. Missing lifecycle
variants remain explicit rather than fabricated.

### A7 — multi-source reuse proof

Onboard a deliberately heterogeneous set drawn from S03, S04, S10 and S07/S05 after refreshing
their current official endpoints and policies. Each source must use an existing generic strategy
unless a separately justified platform capability is genuinely required. Record Recipe size,
thin-plugin LOC and shared strategy use.

## 11. Gate 0 and completion criteria

P9-A engineering completion requires reproducible evidence for:

1. at least one approved strategy carrying S02 official evidence through RawArtifact, VALID
   AcquisitionEvaluation, Document, Opportunity and Evidence;
2. invalid/challenge content retained when policy permits but unable to enter Document;
3. offline replay with manifest/hash/version verification;
4. several materially different official sources using the same control plane;
5. at least three of the first five sources reusing an existing Generic Fetcher;
6. at least 60% of the first five sources requiring only Recipe configuration or a thin discovery
   plugin;
7. no source-specific implementation of transport, retry, persistence, validation, replay or
   health;
8. visible challenge, zero-discovery, selector drift and unexpected-content failure modes;
9. safe degradation on CAPTCHA/login/explicit access control;
10. measured onboarding and source-specific code evidence showing convergence toward Recipe and
    thin logic.

The Blueprint target of 100 sources operating for 14 days with at least 90% requiring no daily
maintenance remains a future Release Qualification target. A7 establishes the platform and early
reuse evidence; it cannot claim that time-based target without the actual observation window.

## 12. Verification and status boundaries

Every Slice uses RED/GREEN tests, a focused verifier, historical contract compatibility,
migration round-trip checks where applicable, scope review and a local commit. Live checks are
never part of default CI.

The final verifier covers:

- root backend quality and tests;
- Phase 2 and Phase 8 historical verifiers;
- P9-A contract, persistence, replay and source-platform tests;
- migration upgrade/downgrade/re-upgrade/drift;
- explicit real replay corpus verification;
- bounded live qualification summaries without secrets or raw response dumps.

Implementation, Engineering Gate, Release Qualification and contract maturity remain independent.
Engineering completion does not establish the 14-day maintenance target, production deployment,
human value or legal approval.

## 13. Explicit non-goals

- no stealth, CAPTCHA solving, login/paywall bypass or access-control circumvention;
- no default-CI access to live official sites;
- no LLM in acquisition or challenge detection;
- no direct Fetcher-to-Opportunity or Fetcher-to-Eligibility path;
- no Opportunity/Eligibility schema changes for a source adapter;
- no unbounded crawler, scheduler, Redis queue or distributed workflow in P9-A;
- no mass 10-100 source expansion before Gate 0 evidence;
- no claim that synthetic fixtures prove real-source accessibility.
