# Phase 5 Public Trust Layer Implementation Plan

> Execution result (2026-08-22): tasks 1-8 were completed through exact candidate SHA
> `492c8b34562dca59c2a66d6e4d3ea769345803ca`; GitHub Actions run `32549701629` completed with all
> six required jobs `success`. Engineering Gate is `CLOSED`; Release Qualification remains
> `NOT_STARTED`; the Phase 5 Public API Contract remains `IMPLEMENTED`, not `STABLE`.

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task
> by task. This task is explicitly authorized for continuous execution without routine manual
> checkpoints. Continue until the Engineering Gate evidence is complete or a real external blocker
> has no safe alternative.

**Goal:** Deliver a governed, read-only public Opportunity index/detail API and responsive Web/PWA
that exposes reproducible trusted fields, official evidence links and change history without any
Phase 6 profile or personal-decision behavior.

**Architecture:** Add one version-bound public catalog allowlist table, project all public facts from
the existing v0.1-v0.4 persistence, expose a GET-only FastAPI application contract, and render it
through Next.js server components. Keep fixed synthetic fixtures visibly labeled and isolate all
PostgreSQL/S3 verification to Phase 5 ports and compose projects.

**Tech stack:** Python 3.14, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL 18, pytest,
Next.js 16, React 19, TypeScript 5.9, Vitest/Testing Library, CSS, Playwright CLI, Docker Compose,
GitHub Actions.

**Exact base:** `8840fe33bd3946a10a5b4448a59f2bf4d7622c3d`

**Branch:** `codex/phase-5-public-trust-layer`

**Non-negotiable workflow:** For every task: write the named failing test first, run it and inspect
the expected failure, implement only enough to pass, run the directed test and risk-matched
regression, stage only the named files, inspect the cached diff, commit, and ordinary-push. Never use
`git add .`, `git add -A`, rebase, force-push, ready, merge or release.

---

## Task 1: Govern public catalog persistence

**Files:**

- Create: `backend/src/deepaha/public_catalog/__init__.py`
- Create: `backend/src/deepaha/public_catalog/models.py`
- Modify: `backend/src/deepaha/db/models.py`
- Create: `backend/migrations/versions/20260822_0005_phase5_public_catalog.py`
- Create: `backend/tests/integration/test_phase5_public_catalog_persistence.py`
- Modify: `backend/tests/integration/test_migrations.py`
- Create: `infra/compose.phase5.yaml`

### Step 1: Create isolated Phase 5 services

Add a compose file with PostgreSQL `18.4-alpine3.23` bound only to `127.0.0.1:55435` and Moto
`5.2.2` bound only to `127.0.0.1:55003`. Use disposable test credentials and PostgreSQL `tmpfs`.

Before starting, verify only the two Phase 5 ports are free. Start with an exact lowercase project
name matching `deepaha-phase5-*`; never inspect, start, stop or down any Phase 2/3/4 project.

```powershell
$phase5Project = "deepaha-phase5-dev-$PID"
Get-NetTCPConnection -State Listen -LocalPort 55435,55003 -ErrorAction SilentlyContinue
docker compose --project-name $phase5Project --file infra/compose.phase5.yaml up -d --wait
```

### Step 2: Write the failing migration and persistence tests

Add tests that expect:

- `public_catalog_entries` exists in ORM metadata and after migration;
- the exact Opportunity/version composite FK and restrictive deletion exist;
- controlled `collection_kind` and `content_use_basis`, positive version, non-empty audit values,
  and `last_verified_at >= approved_at` are enforced;
- an empty `0005` downgrade/re-upgrade succeeds;
- a populated `0005` downgrade refuses without deleting the row;
- no existing v0.1-v0.4 table/column or canonical schema byte is changed.

Run and inspect RED:

```powershell
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_phase5_local_only@127.0.0.1:55435/deepaha"
Push-Location backend
uv run pytest -m integration tests/integration/test_phase5_public_catalog_persistence.py `
  tests/integration/test_migrations.py --strict-markers
Pop-Location
```

Expected: missing table/model/migration failures, not import or infrastructure failures.

### Step 3: Implement the minimal additive model and migration

Implement `PublicCatalogEntry` exactly as the design specifies. Import it through
`deepaha.db.models` so Alembic and metadata checks see it. The migration must create only the new
table/indexes, perform no `UPDATE`/`DELETE`, and refuse downgrade when publication evidence exists.

### Step 4: Verify GREEN and regression

```powershell
Push-Location backend
uv run ruff format --check src/deepaha/public_catalog src/deepaha/db/models.py `
  tests/integration/test_phase5_public_catalog_persistence.py tests/integration/test_migrations.py
uv run ruff check src/deepaha/public_catalog src/deepaha/db/models.py `
  tests/integration/test_phase5_public_catalog_persistence.py tests/integration/test_migrations.py
uv run mypy src/deepaha/public_catalog src/deepaha/db/models.py `
  tests/integration/test_phase5_public_catalog_persistence.py tests/integration/test_migrations.py
uv run alembic upgrade head
uv run pytest -m integration tests/integration/test_phase5_public_catalog_persistence.py `
  tests/integration/test_migrations.py --strict-markers
uv run alembic check
Pop-Location
git diff --check
```

### Step 5: Commit and push exact files

```powershell
git add -- backend/src/deepaha/public_catalog/__init__.py `
  backend/src/deepaha/public_catalog/models.py backend/src/deepaha/db/models.py `
  backend/migrations/versions/20260822_0005_phase5_public_catalog.py `
  backend/tests/integration/test_phase5_public_catalog_persistence.py `
  backend/tests/integration/test_migrations.py infra/compose.phase5.yaml
git diff --cached --check
git commit -m "feat(phase5): govern public catalog persistence"
git push origin codex/phase-5-public-trust-layer
```

Keep the exact Phase 5 compose project running only if the next task immediately needs it;
otherwise down only `$phase5Project` in a `finally` block.

---

## Task 2: Build the deterministic public projection service

**Files:**

- Create: `backend/src/deepaha/public_catalog/schemas.py`
- Create: `backend/src/deepaha/public_catalog/cursor.py`
- Create: `backend/src/deepaha/public_catalog/service.py`
- Create: `backend/tests/public_catalog/__init__.py`
- Create: `backend/tests/public_catalog/test_cursor.py`
- Create: `backend/tests/integration/test_phase5_public_catalog_service.py`
- Create: `backend/tests/fixtures/public_catalog/phase5-public-catalog.json`
- Create: `backend/tests/fixtures/public_catalog/phase5-public-catalog.manifest.json`
- Create: `backend/tests/public_catalog/support.py`

### Step 1: Write fixed fixture and RED tests

Create three small CC0 synthetic Opportunities with deterministic IDs and bytes. Cover two types,
two regions, multiple statuses, two publication dates, two deadlines, an update/event, an attachment
and locator kinds. The manifest must state `synthetic: true`, `business_truth: false`,
`release_qualification_eligible: false`, license, exact byte SHA-256 and generation purpose.

Write unit tests for cursor round-trip, sort binding, malformed/base64/extra-field rejection and
timezone normalization. Write PostgreSQL tests for:

- only allowlisted, `PUBLISHED`, exact-current-version and complete rows appear;
- stale, internal and incomplete rows do not appear;
- all public card fields and fixture label are projected;
- literal `%`/`_` search, stable ID/title/issuer search, type/status/region filters;
- `PUBLISHED_DESC` and `DEADLINE_ASC` stable ordering;
- cursor pages have no duplicate/skip and invalid cursor is rejected;
- detail evidence resolves EvidenceRef -> Document -> RawArtifact official URL;
- history is ordered and every event evidence reaches an official URL;
- unknown/non-visible ID returns no result;
- storage URI, extracted text URI, review actor, profile/rule/match/eligibility data are absent.

Run RED:

```powershell
Push-Location backend
uv run pytest tests/public_catalog/test_cursor.py --strict-markers
uv run pytest -m integration tests/integration/test_phase5_public_catalog_service.py --strict-markers
Pop-Location
```

### Step 2: Implement application schemas, cursor and service

Use strict Pydantic response models. Validate inherited Opportunity snapshot data rather than
silently coercing incomplete JSON. Cursor JSON has a schema version, selected sort, normalized sort
key and public ID, encoded as URL-safe base64 without executable or pickle content.

Build SQLAlchemy `SELECT` projections only. Escape `\`, `%` and `_` for literal `ILIKE`. Apply the
visibility predicate before filters. Fetch `limit + 1`, generate the next cursor from the last
returned item, and use stored `last_verified_at` for deterministic `reproduced_at`.

### Step 3: Verify GREEN and regression

```powershell
Push-Location backend
uv run ruff format --check src/deepaha/public_catalog tests/public_catalog `
  tests/integration/test_phase5_public_catalog_service.py
uv run ruff check src/deepaha/public_catalog tests/public_catalog `
  tests/integration/test_phase5_public_catalog_service.py
uv run mypy src/deepaha/public_catalog tests/public_catalog `
  tests/integration/test_phase5_public_catalog_service.py
uv run pytest tests/public_catalog/test_cursor.py --strict-markers
uv run pytest -m integration tests/integration/test_phase5_public_catalog_service.py --strict-markers
uv run pytest tests/contracts tests/opportunities -m "not integration and not live_source" `
  --strict-markers
Pop-Location
git diff --check
```

### Step 4: Commit and push exact files

```powershell
git add -- backend/src/deepaha/public_catalog/schemas.py `
  backend/src/deepaha/public_catalog/cursor.py backend/src/deepaha/public_catalog/service.py `
  backend/tests/public_catalog/__init__.py backend/tests/public_catalog/test_cursor.py `
  backend/tests/public_catalog/support.py `
  backend/tests/integration/test_phase5_public_catalog_service.py `
  backend/tests/fixtures/public_catalog/phase5-public-catalog.json `
  backend/tests/fixtures/public_catalog/phase5-public-catalog.manifest.json
git diff --cached --check
git commit -m "feat(phase5): project governed public opportunities"
git push origin codex/phase-5-public-trust-layer
```

---

## Task 3: Expose a GET-only public API

**Files:**

- Create: `backend/src/deepaha/api/public_opportunities.py`
- Modify: `backend/src/deepaha/db/session.py`
- Modify: `backend/src/deepaha/main.py`
- Create: `backend/tests/api/test_public_opportunities.py`
- Create: `backend/tests/integration/test_phase5_public_api_read_only.py`

### Step 1: Write RED API tests

Use a fake service for deterministic route tests and PostgreSQL for the read-only transaction test.
Assert:

- list/detail response models and cache headers;
- query parameter bounds and finite enums;
- `400 application/problem+json` for invalid cursor/query;
- `404 application/problem+json` for unknown/non-visible ID;
- non-sensitive `503` for dependency failure;
- the public prefix contains only GET routes;
- returned JSON has no eligibility, match percentage, model confidence, profile or write action;
- PostgreSQL reports `transaction_read_only = on` and an attempted write fails/rolls back.

Run RED:

```powershell
Push-Location backend
uv run pytest tests/api/test_public_opportunities.py --strict-markers
uv run pytest -m integration tests/integration/test_phase5_public_api_read_only.py --strict-markers
Pop-Location
```

### Step 2: Implement the router and read-only session dependency

Create a short-lived session dependency which begins a transaction, executes
`SET TRANSACTION READ ONLY` on PostgreSQL, yields the session, rolls back and closes. The public
service dependency uses only this session. Map expected public errors to stable problem responses;
do not catch validation/programming errors broadly in the service.

Register the router under `/api/v1/public`. Add no CORS, auth, write or Phase 6 route.

### Step 3: Verify GREEN and regression

```powershell
Push-Location backend
uv run ruff format --check src/deepaha/api/public_opportunities.py src/deepaha/db/session.py `
  src/deepaha/main.py tests/api/test_public_opportunities.py `
  tests/integration/test_phase5_public_api_read_only.py
uv run ruff check src/deepaha/api/public_opportunities.py src/deepaha/db/session.py `
  src/deepaha/main.py tests/api/test_public_opportunities.py `
  tests/integration/test_phase5_public_api_read_only.py
uv run mypy src/deepaha/api/public_opportunities.py src/deepaha/db/session.py `
  src/deepaha/main.py tests/api/test_public_opportunities.py `
  tests/integration/test_phase5_public_api_read_only.py
uv run pytest tests/api tests/public_catalog --strict-markers
uv run pytest -m integration tests/integration/test_phase5_public_api_read_only.py `
  tests/integration/test_phase5_public_catalog_service.py --strict-markers
Pop-Location
git diff --check
```

### Step 4: Commit and push exact files

```powershell
git add -- backend/src/deepaha/api/public_opportunities.py `
  backend/src/deepaha/db/session.py backend/src/deepaha/main.py `
  backend/tests/api/test_public_opportunities.py `
  backend/tests/integration/test_phase5_public_api_read_only.py
git diff --cached --check
git commit -m "feat(phase5): expose read-only public opportunity API"
git push origin codex/phase-5-public-trust-layer
```

---

## Task 4: Build the responsive Web/PWA trust experience

**Files:**

- Modify: `web/app/layout.tsx`
- Modify: `web/app/page.tsx`
- Modify: `web/app/globals.css`
- Create: `web/app/manifest.ts`
- Create: `web/app/opportunities/page.tsx`
- Create: `web/app/opportunities/loading.tsx`
- Create: `web/app/opportunities/error.tsx`
- Create: `web/app/opportunities/[publicId]/page.tsx`
- Create: `web/app/opportunities/[publicId]/loading.tsx`
- Create: `web/app/opportunities/[publicId]/error.tsx`
- Create: `web/app/opportunities/[publicId]/fit-check/page.tsx`
- Create: `web/components/site-header.tsx`
- Create: `web/components/opportunity-card.tsx`
- Create: `web/components/trust-fact.tsx`
- Create: `web/lib/public-opportunities.ts`
- Modify: `web/tests/home.test.tsx`
- Create: `web/tests/public-opportunities.test.tsx`
- Create: `web/tests/opportunity-detail.test.tsx`
- Create: `web/tests/fit-check-boundary.test.tsx`
- Create: `web/tests/status-states.test.tsx`

### Step 1: Write RED component/page tests

Mock only the HTTP boundary, not the component output. Assert:

- approved text wordmark/tagline, skip link and semantic landmarks;
- GET search/filter/sort form with labeled controls and reproducible query values;
- cards show stable ID, issuer, type/region, status, published/deadline/verified dates;
- fixture banner is explicit;
- empty state is distinct from error; loading states have visible status text;
- detail shows official entry, attachments, locator/evidence identity and chronological history;
- external official links use safe `target="_blank" rel="noreferrer"`;
- fit-check page explicitly says Phase 6 is unavailable and contains no form;
- no eligibility state, match percentage, model confidence, personal recommendation or profile API
  claim appears anywhere.

Run RED:

```powershell
Push-Location web
corepack pnpm test
Pop-Location
```

### Step 2: Implement the minimum server-rendered experience

Use a typed fetch client with `DEEPAHA_API_BASE_URL`, defaulting only for local development. Throw
for non-OK responses so `error.tsx` is exercised; preserve empty result semantics. Use native links,
forms, lists, `time`, `dl`, `nav`, `main`, `section` and `ol` elements before ARIA additions.

The manifest claims only a standalone shell. Use a text wordmark; do not copy or transform the raw
watermarked logo and do not introduce a new logo asset.

Implement the Phase 5 tokens described in the design. Validate contrast rather than sampling colors
from posters. Use a content-first responsive grid, 44 px targets, 3 px `:focus-visible`, reduced
motion and no horizontal overflow.

### Step 3: Verify GREEN and Web regression

```powershell
Push-Location web
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
corepack pnpm build
Pop-Location
git diff --check
```

### Step 4: Commit and push exact files

```powershell
git add -- web/app/layout.tsx web/app/page.tsx web/app/globals.css web/app/manifest.ts `
  web/app/opportunities/page.tsx web/app/opportunities/loading.tsx `
  web/app/opportunities/error.tsx web/app/opportunities/[publicId]/page.tsx `
  web/app/opportunities/[publicId]/loading.tsx `
  web/app/opportunities/[publicId]/error.tsx `
  web/app/opportunities/[publicId]/fit-check/page.tsx `
  web/components/site-header.tsx web/components/opportunity-card.tsx `
  web/components/trust-fact.tsx web/lib/public-opportunities.ts `
  web/tests/home.test.tsx web/tests/public-opportunities.test.tsx `
  web/tests/opportunity-detail.test.tsx web/tests/fit-check-boundary.test.tsx `
  web/tests/status-states.test.tsx
git diff --cached --check
git commit -m "feat(phase5): build responsive public trust web"
git push origin codex/phase-5-public-trust-layer
```

---

## Task 5: Add isolated verifier and remote CI gate

**Files:**

- Create: `scripts/verify-phase5.ps1`
- Create: `backend/tests/test_phase5_verifier_scope.py`
- Modify: `.github/workflows/ci.yml`

### Step 1: Write RED verifier-scope tests

Assert the script and workflow:

- require `deepaha-phase5-*` project names;
- use only `infra/compose.phase5.yaml`, 55435 and 55003;
- contain none of 55432/55000, 55433/55001, 55434/55002 or upstream project names;
- clean only the exact Phase 5 project in `finally`;
- run root verification, full migration/integration/API/public-catalog tests, contract compatibility,
  downgrade/re-upgrade, Alembic drift and Web build;
- add a `phase5-public-trust` job and include the Phase 5 branch in push triggers.

Run RED:

```powershell
Push-Location backend
uv run pytest tests/test_phase5_verifier_scope.py --strict-markers
Pop-Location
```

### Step 2: Implement the verifier and CI job

Follow the scoped cleanup and port ownership pattern of prior verifiers, replacing every identifier
with Phase 5 values. Do not call a Phase 1-4 verifier. Print evidence boundary lines that say
synthetic fixture only, Release Qualification `NOT_STARTED` and no `STABLE` claim.

### Step 3: Run the complete isolated verifier

```powershell
$env:COMPOSE_PROJECT_NAME = "deepaha-phase5-engineering-gate"
powershell -ExecutionPolicy Bypass -File scripts/verify-phase5.ps1
Remove-Item Env:COMPOSE_PROJECT_NAME
```

Inspect the actual output. Expected minimum evidence includes all root checks, Phase 5 tests,
migration round trips, `alembic check` and scoped cleanup. Then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

### Step 4: Commit and push exact files

```powershell
git add -- scripts/verify-phase5.ps1 backend/tests/test_phase5_verifier_scope.py `
  .github/workflows/ci.yml
git diff --cached --check
git commit -m "test(phase5): add isolated verifier and CI gate"
git push origin codex/phase-5-public-trust-layer
```

---

## Task 6: Seed disposable browser data and perform real-browser QA

**Files:**

- Create: `backend/tests/public_catalog/seed_phase5_browser.py`
- Create: `docs/gates/phase-5/browser-verification.md` initially as an evidence worksheet

### Step 1: Add and test the deterministic browser seed helper

Reuse the test fixture loader and insert only the three governed synthetic records into the
disposable Phase 5 database. The helper must refuse a database URL whose host/port is not
`127.0.0.1:55435`, and must print `SYNTHETIC_FIXTURE_ONLY` plus the inserted count.

Write its guard assertion before implementation in the closest Phase 5 integration test, run RED,
then GREEN.

### Step 2: Start only disposable Phase 5 services and applications

Use a unique `deepaha-phase5-browser-*` project. Migrate and seed PostgreSQL 55435. Start Uvicorn on
an available non-upstream application port and Next.js on another available application port with
`DEEPAHA_API_BASE_URL` set to the Uvicorn URL. Record process IDs and terminate only those exact
processes after QA.

### Step 3: Use Playwright CLI for real rendered checks

First check `npx` availability as required by the Playwright skill. Use the bundled wrapper with one
named session. Verify at widths 375x812 and 1440x900:

- home -> list -> detail -> official/evidence/history -> fit-check boundary;
- search, each finite filter, sort and next-page URL;
- populated, empty and controlled error state;
- keyboard tab order, visible focus, skip link and Enter activation;
- no horizontal overflow, no clipped content and readable date/status labels;
- no personal eligibility, percentage, model confidence, profile form or write request;
- fixture banner remains visible on list and detail.

Capture one mobile and one desktop screenshot to a temporary repository-external directory for
inspection. Do not commit screenshots, browser profiles, cookies or traces.

### Step 4: Record truthful browser evidence

Fill `browser-verification.md` with exact viewport, route, outcome, date, fixture count and negative
assertions. Label it local synthetic engineering evidence only. Do not close the Gate yet.

### Step 5: Commit and push exact files

```powershell
git add -- backend/tests/public_catalog/seed_phase5_browser.py `
  backend/tests/integration/test_phase5_public_catalog_service.py `
  docs/gates/phase-5/browser-verification.md
git diff --cached --check
git commit -m "test(phase5): verify the rendered public trust flow"
git push origin codex/phase-5-public-trust-layer
```

---

## Task 7: Review scope, security, license, privacy and implementation diff

**Files:**

- Create: `docs/gates/phase-5/code-review.md`
- Create: `docs/gates/phase-5/security-and-compliance.md`
- Create: `docs/gates/phase-5/test-summary.md`
- Create: `docs/gates/phase-5/deferred-decisions.md`
- Create: `docs/gates/phase-5/operations.md`
- Create: `docs/gates/phase-5/acceptance-results.md`
- Create: `docs/gates/phase-5/README.md`

### Step 1: Run review scans before writing conclusions

Inspect `8840fe33..HEAD` and record actual results:

- every changed path maps to Phase 5;
- migrations contain no old-row `UPDATE`/`DELETE`;
- public router is GET-only and responses omit internal/user fields;
- no tracked database/object/cache/build/cookie/token/secret or browser artifact;
- no unlicensed original content; synthetic manifest hash matches bytes;
- Phase 5 scripts/config contain no upstream fixed ports or project names;
- v0.1-v0.4 schema trees are byte-identical to the exact base;
- Web strings contain no fake metrics, eligibility percentages or Phase 6 claims;
- review the complete `ui-ux-pro-max/references/pro-rules.md` and apply its pre-delivery checklist;
- review the implementation for Critical/Important findings and fix any via a separate RED/GREEN
  commit before proceeding.

### Step 2: Run final local verification from fresh output

```powershell
$env:COMPOSE_PROJECT_NAME = "deepaha-phase5-final-candidate"
powershell -ExecutionPolicy Bypass -File scripts/verify-phase5.ps1
Remove-Item Env:COMPOSE_PROJECT_NAME
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
git status --short
```

Do not reuse earlier output. Record exact counts and timestamps from this run.

### Step 3: Write Gate evidence without premature closure

Populate the seven Gate documents. Before exact-SHA remote CI succeeds, record:

- Implementation `IMPLEMENTED` if code and local verification actually exist;
- Engineering Gate `OPEN` with remote exact-SHA CI as the remaining item;
- Release Qualification `NOT_STARTED`;
- Phase 5 Public API Contract Maturity `IMPLEMENTED` (not `STABLE`);
- synthetic fixture and browser evidence boundaries.

### Step 4: Commit and push exact files

```powershell
git add -- docs/gates/phase-5/README.md docs/gates/phase-5/acceptance-results.md `
  docs/gates/phase-5/code-review.md docs/gates/phase-5/test-summary.md `
  docs/gates/phase-5/browser-verification.md `
  docs/gates/phase-5/security-and-compliance.md `
  docs/gates/phase-5/deferred-decisions.md docs/gates/phase-5/operations.md
git diff --cached --check
git commit -m "docs(phase5): record engineering gate candidate"
git push origin codex/phase-5-public-trust-layer
```

---

## Task 8: Create stacked draft PR and qualify the exact Engineering Gate SHA

**Files:**

- Modify after CI evidence: `docs/gates/phase-5/README.md`
- Modify after CI evidence: `docs/gates/phase-5/acceptance-results.md`
- Modify after CI evidence: `docs/gates/phase-5/code-review.md`
- Modify after CI evidence: `docs/gates/phase-5/test-summary.md`
- Modify after CI evidence: `docs/superpowers/specs/2026-08-22-phase-5-public-trust-layer-design.md`

### Step 1: Confirm clean synchronization and Phase 4 boundary

```powershell
git status --branch --short
git rev-parse HEAD
git rev-parse origin/codex/phase-5-public-trust-layer
git merge-base --is-ancestor 8840fe33bd3946a10a5b4448a59f2bf4d7622c3d HEAD
```

Re-fetch PR #4 and confirm `OPEN/DRAFT/UNMERGED` and exact Phase 4 head. Stop if the stacked base has
changed unexpectedly.

### Step 2: Create the stacked draft PR

Use the GitHub connector to create:

- base: `codex/phase-4-rules-eligibility-evaluation`
- head: `codex/phase-5-public-trust-layer`
- draft: `true`
- body: exact base/head, four axes, local commands/counts, browser evidence, synthetic boundary,
  explicit Phase 6 exclusion, no Phase 2 access, Release Qualification missing evidence.

Keep it open/draft/unmerged.

### Step 3: Wait for exact-SHA GitHub Actions

Fetch workflow runs for the exact candidate SHA and wait until all required jobs are completed.
Expected jobs:

- `backend-quality`
- `web-quality`
- `integration`
- `phase3-resolution`
- `phase4-eligibility`
- `phase5-public-trust`

If any job fails, invoke `superpowers:systematic-debugging`, identify the first causal failure, add a
reproducing RED test where applicable, make the minimum fix, rerun local verification, commit/push,
and restart exact-SHA qualification. Never relabel a failed run as success.

### Step 4: Close only the Engineering Gate

After all exact-SHA jobs succeed, update the five evidence/design files with the exact candidate SHA,
run ID/job conclusions and final four axes:

- Implementation `IMPLEMENTED`
- Engineering Gate `CLOSED`
- Release Qualification `NOT_STARTED`
- Phase 5 Public API Contract Maturity `IMPLEMENTED` (not `STABLE`)

Commit and push exact files:

```powershell
git add -- docs/gates/phase-5/README.md docs/gates/phase-5/acceptance-results.md `
  docs/gates/phase-5/code-review.md docs/gates/phase-5/test-summary.md `
  docs/superpowers/specs/2026-08-22-phase-5-public-trust-layer-design.md
git diff --cached --check
git commit -m "docs(phase5): close the engineering gate"
git push origin codex/phase-5-public-trust-layer
```

Because this governance commit changes the exact SHA, wait again for every required job on the new
final SHA. Update the PR body with that final SHA/run and each job conclusion. If documenting the
second run would create another commit loop, keep the immutable GitHub run evidence in the PR body
and have repository evidence refer to the preceding exact successful implementation candidate plus
the docs-only relationship, matching prior Gate practice.

### Step 5: Use branch-finishing procedure without integration

Invoke `superpowers:finishing-a-development-branch`. The user has already selected the equivalent
of “keep the branch/stacked draft PR”; do not present merge options, ready the PR, merge or delete the
worktree. Verify final branch cleanliness and remote equality, then report exact evidence and all
deferred real qualification work.

---

## Final success checklist

- exact Phase 5 start is still an ancestor; no rebase/force/history rewrite;
- branch is clean and equals its remote;
- Phase 4 PR #4 remains open/draft/unmerged;
- public catalog is explicitly governed and finite;
- API is GET-only/read-only and all hard facts reach official evidence;
- search/filter/sort/cursor and error/empty/loading behavior are deterministic;
- mobile/desktop/keyboard/contrast/browser verification is recorded;
- no personal qualification, ranking, percentage, profile or Phase 6 behavior exists;
- no Phase 2 live port/project was accessed, modified, stopped or occupied;
- isolated local verifier and exact final SHA remote jobs are successful;
- Phase 5 axes are truthful and Release Qualification remains `NOT_STARTED` without 200 real Gold.
