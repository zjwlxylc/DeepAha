# P9-A Source Acquisition Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement
> this plan task-by-task. Use `superpowers:test-driven-development` for every behavior change,
> `superpowers:systematic-debugging` for unexpected failures, and
> `superpowers:verification-before-completion` before each Slice completion claim and commit.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend DeepAha's deterministic Phase 2-8 core with a reusable, auditable, replayable,
health-monitored and policy-bound Source Acquisition Platform, then prove across S02 plus four
heterogeneous official sources that onboarding work is converging toward Recipe/configuration and
thin discovery logic instead of duplicated collection systems.

**Architecture:** Add a thin `deepaha.acquisition` control plane above the existing SourceEndpoint,
collector, RawArtifact and Document services. Preserve CaptureObservation as transport truth; add
one immutable AcquisitionEvaluation per successful acquisition observation for semantic truth.
Drive generic fetchers and deterministic validation from strict JSON Source Recipes. Parse only
VALID artifacts, retain policy-permitted invalid artifacts for audit, and derive replay, health and
integration-cost evidence from the common contracts. Browser is a conditional strategy selected
only if A5 evidence proves standard public rendering is both permitted and necessary.

**Tech Stack:** Python 3.14, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL 18, httpx2, lxml,
optional Playwright Chromium only after A5, pytest, Ruff, mypy, PowerShell, Docker Compose and Git.

**Spec:** `docs/superpowers/specs/2026-08-23-source-acquisition-platform-design.md`

**Exact base:** `f704c2d` (design commit), with A0 ancestor
`9d051044defaa2f41ad91f9aaf6e891742aaf8fa` and local main/origin/main base
`cedce6f229dc341bf20107200b61e1f197b0d3d7`.

**Branch:** `codex/source-acquisition-platform`

## Global Constraints

- Re-read `AGENTS.md` and the approved spec before A1 and final Gate 0 closeout.
- Do not create another worktree; do not fetch, merge, rebase, stash, push, deploy or modify
  `D:/DeepAha` user files.
- Preserve historical v0.1-v0.7 contracts, Phase 2 CaptureObservation semantics and all Phase 8
  behavior. New schema is additive.
- Keep Source authority (`tier`) separate from acquisition/evidence use (`usage_role`).
- A Fetcher never creates Document, Evidence, Opportunity or eligibility facts. The orchestrator
  invokes the existing Document service only after a persisted VALID evaluation.
- Persist policy-permitted challenge/invalid bytes as RawArtifact; never transform HTTP 200
  challenge content into a normal Document. CAPTCHA, login and explicit access control stop the
  plan without bypass.
- No credentials, cookies, tokens, complete bodies or sensitive headers in contracts, logs,
  diagnostics, recipes, manifests or Git.
- Real bytes remain in the configured controlled object store. Git contains only public URLs,
  hashes, object locators, versions and expected outcomes unless an existing explicit open licence
  permits the current Phase 2 fixture policy.
- Default CI is network-free. Live tests require `DEEPAHA_ALLOW_LIVE_SOURCE_CHECK=true`, explicit
  endpoint policy approval and the `live_source` marker.
- A7 is an Engineering Gate proof, not the 100-source/14-day Release Qualification and not a claim
  of complete nationwide coverage.
- For each task: write the failing test, run it and inspect RED, implement the minimum, run focused
  GREEN plus risk regression, inspect the exact diff, and make a local Slice-scoped commit.
- Use `apply_patch` for source/document edits and stage exact paths only.

---

## File Map

### Common acquisition control plane

- `backend/src/deepaha/acquisition/contracts.py`: immutable Fetch, evaluation, Recipe and replay
  value contracts.
- `backend/src/deepaha/acquisition/models.py`: additive semantic-evaluation and later run/evidence
  persistence.
- `backend/src/deepaha/acquisition/fetchers.py`: generic static/structured/manual and conditional
  Browser Fetchers; adapters over existing transport safeguards.
- `backend/src/deepaha/acquisition/validation.py`: deterministic generic checks plus declarative
  expectations.
- `backend/src/deepaha/acquisition/evaluations.py`: immutable idempotent evaluation persistence.
- `backend/src/deepaha/acquisition/recipes.py`: strict JSON Recipe loader and cross-checks against
  SourceEndpoint policy.
- `backend/src/deepaha/acquisition/discovery.py`: generic HTML/structured link discovery and URL
  policy enforcement; source plugins may implement discovery/canonicalization only.
- `backend/src/deepaha/acquisition/orchestrator.py`: bounded Fetch Plan state machine and VALID-only
  Document transition.
- `backend/src/deepaha/acquisition/replay.py`: manifest/hash/version verification with network off.
- `backend/src/deepaha/acquisition/health.py`: semantic health/drift and integration evidence.
- `backend/src/deepaha/acquisition/cli.py`: bounded qualification/replay commands; no scheduler.

### Persistence and configuration

- `backend/migrations/versions/20260823_0009_source_acquisition_evaluations.py`: A1 additive table.
- `backend/migrations/versions/20260823_0010_source_acquisition_health.py`: A4 additive run and
  integration evidence tables if common persisted run facts cannot be represented by 0009 alone.
- `config/acquisition/recipes.v1.json`: approved recipes for synthetic tests and qualified real
  sources; no secrets or executable code.
- `config/acquisition/real-source-corpus.v1.json`: real-corpus manifest only, never response bytes.
- `docs/gates/source-acquisition-platform/`: A5 feasibility, A6/A7 evidence, health/cost, security,
  code review and Gate 0 status.
- `scripts/verify-source-acquisition-platform.ps1`: isolated P9-A verifier.

---

## A1 — Contracts, validation and companion persistence

### Task 1: Define immutable Fetch and validation contracts

**Files:**

- Create: `backend/src/deepaha/acquisition/__init__.py`
- Create: `backend/src/deepaha/acquisition/contracts.py`
- Create: `backend/tests/acquisition/__init__.py`
- Create: `backend/tests/acquisition/test_contracts.py`

**Interfaces:**

- Enums: `FetchStrategy`, `ValidationStatus`, `ChallengeType`, `SourceUsageRole`.
- Values: `FetchRequest`, `FetchResult`, `ContentExpectations`, `ValidationResult`.
- Contract version is the fixed literal `1.0.0`; all models are frozen and forbid extras.
- `FetchResult` contains normalized request/final URLs, ordered redirect chain, bounded safe
  headers, body bytes or object reference (exactly one), SHA-256, fetch time and stable versions.

- [x] Write RED tests for closed enums, UUIDv7 identifiers, credentials in URLs, duplicate hosts,
  body/reference exclusivity, hash/body agreement, redirect ordering, status/diagnostic coherence,
  bounded headers/metrics and challenge-field coherence.
- [x] Run `uv run pytest tests/acquisition/test_contracts.py -q` from `backend`; inspect the missing
  module failure.
- [x] Implement only the four enums and four frozen Pydantic values needed by those tests.
- [x] Run focused GREEN, `ruff format --check`, `ruff check` and `mypy` on the new files.

### Task 2: Implement deterministic ContentValidator

**Files:**

- Create: `backend/src/deepaha/acquisition/validation.py`
- Create: `backend/tests/acquisition/test_validation.py`
- Create fixtures under: `backend/tests/fixtures/acquisition/synthetic/`

**Behavior:**

- Checks, in deterministic precedence: access denied/auth/CAPTCHA/challenge; empty/short body;
  MIME mismatch; structured parse validity; required/forbidden markers; HTML selectors;
  discovery-count minimum; otherwise VALID.
- Diagnostics contain only stable codes, numeric/boolean metrics and matched marker identifiers,
  never raw body text.
- `expires` or wall-clock behavior does not exist; validation uses only FetchResult and Recipe
  inputs.

- [x] Write RED table tests for VALID, cookie/JavaScript challenge, CAPTCHA, login, access denied,
  unexpected MIME, empty/short response, malformed JSON/XML, missing selector, forbidden marker,
  zero discovery and deterministic repeated evaluation.
- [x] Run focused RED and verify failures are missing behavior, not malformed fixtures.
- [x] Implement `ContentValidator.evaluate(result, expectations) -> ValidationResult` with no LLM,
  network or source-specific branches.
- [x] Run focused GREEN and all existing source/document unit tests.

### Task 3: Add AcquisitionEvaluation contract, model and migration 0009

**Files:**

- Modify: `backend/src/deepaha/acquisition/contracts.py`
- Create: `backend/src/deepaha/acquisition/models.py`
- Modify: `backend/src/deepaha/db/models.py`
- Create: `backend/migrations/versions/20260823_0009_source_acquisition_evaluations.py`
- Create: `backend/tests/integration/test_acquisition_evaluation_persistence.py`
- Modify: `backend/tests/integration/test_migrations.py`

**Persistence invariants:**

- UUIDv7 primary key; unique observation; composite bindings to observation endpoint/source and
  artifact/source; VALID/invalid/challenge check constraints; ordered JSON redirect chain;
  non-negative discovered count; bounded JSON metrics validated in application code.
- Evaluation rows are immutable. Downgrade refuses while any evaluation exists.
- CaptureObservation remains unchanged and historical migration checks remain byte-compatible.

- [x] Write RED contract/database tests for all invariants, cross-source rejection, one evaluation
  per observation, immutability, non-empty downgrade refusal and empty downgrade/re-upgrade/drift.
- [x] Start only the existing isolated Phase 8/P9-compatible PostgreSQL fixture on a free local
  port; run the exact integration RED and inspect the missing revision/table failure.
- [x] Implement model/import and additive 0009 migration without modifying old migration files.
- [x] Run `alembic upgrade head`, focused integration GREEN, empty downgrade to 0008,
  re-upgrade, `alembic check`, Ruff and mypy; clean up only the exact Compose project.

### Task 4: Persist evaluations idempotently and adapt static HTTP results

**Files:**

- Create: `backend/src/deepaha/acquisition/evaluations.py`
- Create: `backend/src/deepaha/acquisition/fetchers.py`
- Modify minimally: `backend/src/deepaha/sources/collector.py`
- Create: `backend/tests/acquisition/test_fetchers.py`
- Create: `backend/tests/integration/test_acquisition_evaluation_service.py`

**Interfaces:**

- `EvaluationService.record(command) -> AcquisitionEvaluationSchema` owns its transaction and
  returns the existing row only when every immutable input matches; conflict fails closed.
- `StaticHttpFetcher.fetch(request) -> FetchResult` delegates endpoint policy, DNS/IP, redirect,
  conditional request, MIME, size, rate and retry enforcement to the existing collector.
- Extend `CollectionRunner.collect` only enough to accept an optional policy-bound requested URL
  and expose its ordered redirect chain; the default endpoint behavior remains identical.

- [x] Write RED tests proving exact replay, conflicting replay, no evaluation for transport
  failure, redirect-chain preservation, dynamic same-host acceptance and credential/private-host/
  unapproved-host rejection.
- [x] Run RED and inspect intended assertion/missing-interface failures.
- [x] Implement the service and adapter without copying collector policy code.
- [x] Run focused GREEN plus all Phase 2 collector/collection/persistence tests.

### Task 5: Enforce the VALID-only Document transition

**Files:**

- Create: `backend/src/deepaha/acquisition/pipeline.py`
- Create: `backend/tests/integration/test_acquisition_document_gate.py`

**Interface:**

- `advance_valid_artifact(session_factory, object_store, evaluation_id) -> ParseDocumentResult`
  loads the immutable evaluation and RawArtifact, refuses any status other than VALID, and invokes
  the existing `DocumentService`; it does not create Opportunity facts.

- [x] Write RED integration tests proving VALID parses, challenge/unexpected/zero-discovery do not
  create ParseAttempt or Document, retained RawArtifact remains readable, and exact replay does not
  duplicate Document.
- [x] Run RED, implement the smallest gate, and run focused GREEN plus document service regression.
- [x] Run the A1 focused verifier set, `git diff --check`, exact staged scope review and local commit
  `feat: add source acquisition contracts and validation`.

---

## A2 — Source Recipe and bounded Orchestrator

### Task 6: Define and load strict Source Recipes

**Files:**

- Extend: `backend/src/deepaha/acquisition/contracts.py`
- Create: `backend/src/deepaha/acquisition/recipes.py`
- Create: `backend/tests/acquisition/test_recipes.py`
- Create: `backend/tests/fixtures/acquisition/recipes-valid.json`
- Create: `backend/tests/fixtures/acquisition/recipes-invalid.json`
- Create: `config/acquisition/recipes.v1.json`

**Recipe fields:** source/endpoint IDs, recipe/version, usage role, ordered strategy plan, content
expectations, discovery kind/selectors, pagination/detail/attachment limits, allowed URL patterns,
health thresholds, active/verified timestamps. No credentials or arbitrary code/plugin path.

- [ ] Write RED tests for strict schema, duplicate identities, version replay/conflict, endpoint
  ownership, source/endpoint active state, host/media/browser-policy compatibility, finite budgets,
  authority/usage separation and secret/executable-key rejection.
- [ ] Implement deterministic UTF-8 JSON loader and `validate_recipe_against_endpoint`.
- [ ] Run focused GREEN and registry-manifest regression.

### Task 7: Implement generic discovery and URL policy

**Files:**

- Create: `backend/src/deepaha/acquisition/discovery.py`
- Create: `backend/tests/acquisition/test_discovery.py`

**Interfaces:**

- `discover_links(content, media_type, recipe) -> tuple[DiscoveredLink, ...]` supports declarative
  HTML CSS link extraction and structured JSON/XML path extraction.
- `canonicalize_discovered_url` resolves relative links, strips fragments, preserves meaningful
  query parameters, rejects credentials/non-http schemes/unapproved hosts and de-duplicates while
  retaining first-seen order.
- Thin plugins, if later necessary, implement only a typed discovery/canonicalization protocol.

- [ ] Write RED tests for relative/absolute/detail/attachment links, pagination caps, duplicate
  links, off-host and private/local URLs, malformed content and selector drift.
- [ ] Implement generic discovery without a source-name/host conditional.
- [ ] Run focused GREEN and security-focused collector tests.

### Task 8: Implement the bounded Acquisition Orchestrator

**Files:**

- Create: `backend/src/deepaha/acquisition/orchestrator.py`
- Create: `backend/tests/acquisition/test_orchestrator.py`
- Create: `backend/tests/integration/test_acquisition_orchestrator.py`

**State machine:** load active endpoint/Recipe; run strategies in declared order under a total
attempt/request/elapsed budget; persist observation/artifact/evaluation; stop on VALID; discover
bounded child requests; parse only VALID; degrade/stop on explicit statuses; record a stable
summary. A fallback cannot weaken endpoint policy.

- [ ] Write RED unit tests with fake Fetchers for success, deterministic fallback, exhausted plan,
  CAPTCHA/auth/access-denied stop, challenge fallback only when allowed, total-budget enforcement,
  invalid dynamic URL rejection and stable repeated summary.
- [ ] Write RED PostgreSQL/S3 integration tests for atomic common persistence, RawArtifact dedup,
  evaluation idempotency, VALID-only parsing and no duplicate child request.
- [ ] Implement the minimum orchestrator with injected clock/fetcher registry; no queue/scheduler.
- [ ] Run focused GREEN, all A1 tests, Phase 2 collection/document regressions, Ruff and mypy.
- [ ] Inspect that `acquisition` contains no source host/name branch; local commit
  `feat: orchestrate recipe-driven source acquisition`.

---

## A5 — Real strategy feasibility and decision

### Task 9: Build a bounded qualification command and evidence schema

**Files:**

- Create: `backend/src/deepaha/acquisition/cli.py`
- Create: `backend/tests/acquisition/test_cli.py`
- Create: `scripts/run-source-acquisition-qualification.ps1`
- Create: `docs/gates/source-acquisition-platform/a5-feasibility.md`

**Command guarantees:** explicit live opt-in; endpoint and Recipe IDs; maximum request count;
minimum interval; safe JSON summary only; no response body/header/cookie dump; network off in tests;
nonzero exit on policy/challenge/budget failure.

- [ ] Write RED subprocess tests with fake fetchers proving opt-in, budget and secret/body redaction.
- [ ] Implement command and PowerShell wrapper, then run network-free GREEN.

### Task 10: Refresh S02 policy and execute L0/L1/L2-feasibility/L3 checks

**Files:**

- Modify only if facts changed: `config/sources/phase2-official-endpoints.json`
- Modify: `config/acquisition/recipes.v1.json`
- Complete: `docs/gates/source-acquisition-platform/a5-feasibility.md`
- Create/update manifest skeleton: `config/acquisition/real-source-corpus.v1.json`

- [ ] Re-check S02 public endpoint, robots/use evidence, MIME, redirect and challenge response at
  low frequency. Record UTC/China time, public URLs, status, MIME, bytes/hash and stable result;
  never record cookies/body/secrets.
- [ ] Inspect page source/network declarations and public links for an approved RSS/JSON/XML,
  stable official alternate endpoint or ordinary browser-rendered path. Do not execute or emulate
  challenge code and do not use stealth, proxy, credential or CAPTCHA mechanisms.
- [ ] Decide exactly one route: L0 structured, L1 static, L2 standard Browser, L3 official
  alternative or L4 governed manual. Record rejected routes and stop reasons.
- [ ] Run the chosen Recipe in bounded qualification mode and retain policy-permitted bytes only in
  controlled object storage.
- [ ] Verify the manifest hash/object locator and commit only metadata/evidence with local commit
  `docs: record S02 acquisition feasibility`.

---

## A3 — Conditional Browser or selected compliant fallback

### Task 11A: Implement standard BrowserFetcher only if A5 selects L2

**Files (conditional):**

- Modify: `backend/pyproject.toml`, `backend/uv.lock`
- Extend: `backend/src/deepaha/acquisition/fetchers.py`
- Create: `backend/tests/acquisition/test_browser_fetcher.py`
- Create: `backend/tests/fixtures/acquisition/browser/` synthetic pages

- [ ] Add Playwright only if not already available in an approved project runtime.
- [ ] Write RED tests for ordinary DOM rendering, bounded time/bytes/requests, approved hosts,
  resource filtering, final DOM provenance and immediate stop on CAPTCHA/auth/access control.
- [ ] Implement standard Chromium rendering with no stealth/fingerprint/token/cookie-pool behavior.
- [ ] Run network-free synthetic browser GREEN and orchestrator fallback regression.

### Task 11B: Implement the selected L0/L3/L4 path when Browser is not selected

**Files (conditional):**

- Extend only as needed: `backend/src/deepaha/acquisition/fetchers.py`
- Create/extend tests: `backend/tests/acquisition/test_fetchers.py`
- Modify: `config/acquisition/recipes.v1.json`

- [ ] For L0/L3, write RED tests for structured/official-alternative provenance and the same host,
  MIME, size, retry, validation and RawArtifact guarantees.
- [ ] For L4, write RED tests for actor, approved public URL, hash, policy version, duplicate import,
  and mandatory validation; manual import must not silently become automated health success.
- [ ] Implement only the selected route, run focused GREEN and document why Browser was omitted.

- [ ] Run the A3 selected-path verification and local commit
  `feat: add selected compliant acquisition strategy`.

---

## A4 — Semantic health, drift and integration cost

### Task 12: Persist acquisition run and integration evidence

**Files:**

- Extend: `backend/src/deepaha/acquisition/contracts.py`
- Extend: `backend/src/deepaha/acquisition/models.py`
- Create if needed: `backend/migrations/versions/20260823_0010_source_acquisition_health.py`
- Create: `backend/tests/integration/test_acquisition_health_persistence.py`

**Run facts:** endpoint/Recipe versions, strategy attempts, discovered/validated/parsed/attachment
counts, zero-discovery/drift/manual flags, stable stop reason, start/end time. Integration facts:
Recipe lines, source-specific production LOC, generic capability changes, core schema changes,
onboarding minutes, browser/manual ratios and evidence time.

- [ ] Write RED constraints, immutability/idempotency, cross-source and downgrade tests.
- [ ] Implement additive persistence and migration; never modify an old migration.
- [ ] Run migration round trip, drift, Ruff, mypy and historical migration regression.

### Task 13: Derive semantic health and convergence metrics

**Files:**

- Create: `backend/src/deepaha/acquisition/health.py`
- Create: `backend/tests/acquisition/test_health.py`
- Create: `backend/tests/integration/test_acquisition_health.py`
- Create: `docs/gates/source-acquisition-platform/health-and-cost.md`

- [ ] Write RED fixed-clock tests for accessibility, discovery, fetch integrity, parseability,
  evidenceability, drift, last VALID success, consecutive semantic failures, selector drift,
  zero-discovery and manual/browser ratios.
- [ ] Implement pure derived health values over common observations/evaluations/runs.
- [ ] Add integration-cost computation for first-five reuse ratio and Recipe/thin-plugin ratio; it
  must fail rather than report PASS when evidence is missing.
- [ ] Run focused GREEN plus legacy source-health regression and local commit
  `feat: add acquisition health and integration evidence`.

---

## A6 — S02 real acceptance v2

### Task 14: Implement controlled replay manifests

**Files:**

- Create: `backend/src/deepaha/acquisition/replay.py`
- Create: `backend/tests/acquisition/test_replay.py`
- Create: `backend/tests/integration/test_real_acquisition_replay.py`
- Extend: `config/acquisition/real-source-corpus.v1.json`

- [ ] Write RED tests for manifest schema, missing object, hash/size/version mismatch, wrong
  source/endpoint/artifact binding, forbidden embedded body, network disabled and deterministic
  expected evaluation/discovery/parse outcomes.
- [ ] Implement controlled-store loader and replay runner; absence of real bytes yields explicit
  NOT_RUN/BLOCKED evidence, never synthetic PASS.
- [ ] Run synthetic manifest GREEN and the controlled real-corpus replay when storage is available.

### Task 15: Carry S02 through the real evidence chain

**Files:**

- Modify: `config/acquisition/recipes.v1.json`
- Modify: `config/acquisition/real-source-corpus.v1.json`
- Create: `docs/gates/source-acquisition-platform/a6-s02-acceptance.md`
- Add only genuinely necessary thin discovery logic under:
  `backend/src/deepaha/acquisition/plugins/`
- Add corresponding tests under: `backend/tests/acquisition/plugins/`

- [ ] Acquire 3-5 current S02 lifecycle samples when they actually exist; if current corrections,
  attachments or cancellations are unavailable, record the missing variant without fabrication.
- [ ] Prove RawArtifact hash/object persistence, VALID evaluation, Document parse/locator replay,
  detail/attachment relationship and exact dedup.
- [ ] Use the existing Opportunity resolution service to carry at least one real S02 Document/
  Evidence candidate into a stable Opportunity/version path; do not add Fetcher-to-Opportunity
  shortcuts or source-specific Opportunity schema.
- [ ] Replay with network disabled and prove identical evaluation/discovery/Document/Opportunity
  identity outcomes.
- [ ] Feed the retained challenge/zero-discovery sample through the common validator and prove it
  cannot create Document.
- [ ] Run A6 focused verification, scope review and local commit
  `test: qualify S02 acquisition and replay`.

---

## A7 — Multi-source reuse proof and Gate 0

### Task 16: Qualify and onboard four heterogeneous official sources

**Files:**

- Modify: `config/sources/phase2-official-endpoints.json` only for freshly verified policy facts.
- Modify: `config/acquisition/recipes.v1.json`
- Modify: `config/acquisition/real-source-corpus.v1.json`
- Create: `docs/gates/source-acquisition-platform/a7-multi-source-evidence.md`
- Add thin discovery plugins/tests only when declarative discovery is demonstrably insufficient.

- [ ] Refresh and qualify S03, S04, S10 and one of S07/S05 (or document and substitute the nearest
  approved heterogeneous official endpoint if a named source is currently unavailable).
- [ ] For each source, record strategy, endpoint policy, Recipe lines, source-specific production
  LOC, generic changes, onboarding time, browser/manual use, sample hashes and replay result.
- [ ] Require each source to pass common validation, RawArtifact persistence, Document parsing and
  offline replay. At least one source must exercise an attachment or structured feed when current
  official evidence permits it.
- [ ] Reject any proposed plugin that implements transport, retry, persistence, validation,
  replay, health or evidence storage.
- [ ] Compute Gate metrics from persisted/manifested facts: at least 3/5 reuse an existing generic
  Fetcher and at least 3/5 (60%) use Recipe-only or Recipe plus thin discovery logic.

### Task 17: Add the isolated P9-A verifier and evidence package

**Files:**

- Create: `scripts/verify-source-acquisition-platform.ps1`
- Create: `backend/tests/test_source_acquisition_verifier_scope.py`
- Create/update:
  - `docs/gates/source-acquisition-platform/README.md`
  - `docs/gates/source-acquisition-platform/test-summary.md`
  - `docs/gates/source-acquisition-platform/security-and-compliance.md`
  - `docs/gates/source-acquisition-platform/code-review.md`
  - `docs/gates/source-acquisition-platform/acceptance-results.md`
  - `docs/gates/source-acquisition-platform/deferred-decisions.md`

- [ ] Write RED scope tests proving the verifier runs P9-A unit/integration/migration/replay tests,
  prior Phase 2 and Phase 8 verifiers, Ruff/mypy and diff checks; default mode must exclude live
  network, while explicit qualification mode is bounded and redacted.
- [ ] Implement an isolated PostgreSQL/S3 Compose project with unique free ports or reuse the
  repository's established newest-phase isolation pattern without touching other projects.
- [ ] Run the verifier from a clean working tree except evidence-doc updates and capture actual
  command counts/results.
- [ ] Run the full Phase 8 verifier separately and record actual output.
- [ ] Run controlled real replay separately; record PASS/FAIL/BLOCKED without substituting
  synthetic fixtures.

### Task 18: Final review, verification and local delivery commits

- [ ] Review every changed line against the approved design and prohibited-scope list; confirm no
  source-specific collection system, eligibility shortcut, stealth/bypass, scheduler or live CI.
- [ ] Run full root `scripts/verify.ps1`, `scripts/verify-phase2.ps1`,
  `scripts/verify-phase8.ps1` and `scripts/verify-source-acquisition-platform.ps1`; read the final
  output, do not infer success from exit code alone.
- [ ] Run migration upgrade/downgrade/re-upgrade/drift on an exact isolated empty project and the
  non-empty downgrade-refusal integration test.
- [ ] Run code review and `superpowers:verification-before-completion`; resolve every in-scope
  finding and re-run affected checks.
- [ ] Mark implementation `IMPLEMENTED` and Engineering Gate `CLOSED` only if all ten Gate 0
  criteria have reproducible evidence. Otherwise record the exact OPEN criteria and do not
  overclaim.
- [ ] Stage only exact final docs/verifier files, inspect cached diff/check, and create local commit
  `docs: close source acquisition platform gate` only if Gate 0 is actually closed; otherwise use
  an accurate evidence-status commit message.
- [ ] Do not push, merge, deploy or continue beyond A7.
