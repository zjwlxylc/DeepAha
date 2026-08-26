# DeepAha Local Manual Test Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build safe Windows double-click start/stop entries for a persistent, synthetic Phase 6–8 local manual-test environment.

**Architecture:** A PowerShell orchestrator owns lifecycle and an exact runtime manifest, Docker Compose owns disposable PostgreSQL/S3, a Python seed composes existing fixtures, and a Playwright host opens isolated authenticated Chromium contexts. Existing application APIs and Web routes remain unchanged.

**Tech Stack:** Windows PowerShell 5.1+, Docker Compose, Python 3.14/uv, FastAPI/Alembic/PostgreSQL 18, Node.js 24/Corepack/pnpm, Next.js 16, Playwright Chromium.

**Spec:** `docs/superpowers/specs/2026-08-23-local-manual-test-launcher-design.md`

## Global Constraints

- No Phase 2 live observation, automation creation/restoration, real provider, production deployment, merge, rebase, commit, or push.
- Delivery target is only `TEST_INBOX`; real participants remain `0`; release decision remains `HOLD_MISSING_HUMAN_EVIDENCE`.
- Cleanup may target only the exact project and processes proven by root, hash, labels, PID, creation time, and command line.
- Do not change production API/Web authentication routes or existing Phase 6–8 verifier behavior.
- First professional term in user-facing Chinese copy uses Chinese with English in parentheses.

---

### Task 1: Combined synthetic seed

**Files:**
- Create: `backend/tests/manual/__init__.py`
- Create: `backend/tests/manual/seed_local_manual.py`
- Create: `backend/tests/manual/test_seed_local_manual.py`

**Interfaces:**
- Consumes: existing `persist_phase6_fixture`, Phase 7 profile/matching helpers, `persist_reviewer`, and Phase 8 prepare/resolve/govern/worker helpers.
- Produces: `seed_local_manual(database_url: str) -> LocalManualIdentity` and a CLI that writes one JSON identity document to a caller-supplied path.

- [ ] **Step 1: Write failing unit tests** for exact database URL rejection, identity JSON shape, and reuse refusal. Expected break: `tests.manual.seed_local_manual` does not exist.
- [ ] **Step 2: Run RED:** `uv run pytest tests/manual/test_seed_local_manual.py -v`; expect import failure for the missing module.
- [ ] **Step 3: Implement minimal seed:** validate `127.0.0.1:55439/deepaha`, require empty governed tables, persist Phase 6/7 identity and Phase 8 reminder, assert `TEST_INBOX`, write credentials only to the requested ignored file, and print only synthetic boundary/status lines.
- [ ] **Step 4: Run GREEN unit tests:** the same pytest command must pass.
- [ ] **Step 5: Run the integration seed twice against migrated dedicated PostgreSQL:** first run succeeds with Phase 6/7 and Phase 8 identities; second run fails with the documented empty-scope error.

### Task 2: Lifecycle ownership and double-click entries

**Files:**
- Create: `scripts/tests/local-manual-test.Tests.ps1`
- Create: `scripts/local-manual-test.ps1`
- Create: `infra/compose.local-manual.yaml`
- Create: `启动 DeepAha 本地人工测试.cmd`
- Create: `停止 DeepAha 本地人工测试.cmd`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: Task 1 seed CLI and fixed ports `55439`, `55007`, `8009`, `3089`.
- Produces: `Start`, `Stop`, and internal testable ownership functions plus `.deepaha-local-manual/runtime.json`.

- [ ] **Step 1: Write failing PowerShell tests** exercising project-name derivation, state-root mismatch rejection, PID creation-time/command mismatch rejection, exact process-tree ordering, and no-state idempotent stop. Expected break: lifecycle functions are absent.
- [ ] **Step 2: Run RED:** `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/local-manual-test.Tests.ps1`; expect a missing-script/function failure.
- [ ] **Step 3: Implement minimal lifecycle:** prerequisite/port checks, exact Compose ownership, dependency setup, migration, seed, process start/readiness, runtime manifest, failure cleanup, and Chinese status/error copy.
- [ ] **Step 4: Add thin CMD wrappers** that locate their own repository root and invoke PowerShell with `Start` or `Stop`; they pause only when launched interactively.
- [ ] **Step 5: Run GREEN PowerShell tests** and confirm all assertions pass without starting Docker or killing real processes.

### Task 3: Authenticated browser host

**Files:**
- Create: `web/scripts/open-local-manual-browser.mjs`
- Modify: `scripts/local-manual-test.ps1`

**Interfaces:**
- Consumes: identity JSON with `personal_session`, `reviewer_session`, `reminder_session`, `personal_public_id`, and local Web origin.
- Produces: two isolated headed Chromium contexts and a host process whose descendants are tracked by Task 2.

- [ ] **Step 1: Extend PowerShell tests with a failing assertion** that browser launch receives the identity path without logging its contents and is recorded as an owned process.
- [ ] **Step 2: Run RED:** PowerShell test must fail because the browser host is absent.
- [ ] **Step 3: Implement browser host:** read and delete identity JSON, set server-only cookie names in two contexts, open public/personal/review pages in the main context and reminders in the separate context, and remain alive until contexts close.
- [ ] **Step 4: Run GREEN PowerShell tests** and `node --check web/scripts/open-local-manual-browser.mjs`.

### Task 4: Documentation and verification wiring

**Files:**
- Create: `docs/development/local-manual-testing.md`
- Modify: `README.md`
- Modify: `scripts/verify.ps1`

**Interfaces:**
- Consumes: Tasks 1–3 entry names, boundaries, and verification commands.
- Produces: nontechnical usage instructions and root invocation of the safe PowerShell unit suite.

- [ ] **Step 1: Update root verifier** to execute `scripts/tests/local-manual-test.Tests.ps1` before language-specific checks.
- [ ] **Step 2: Document double-click start/stop, synthetic identities, `TEST_INBOX`, logs, retry/recovery, and unchanged release qualification without exposing tokens or requiring commands.
- [ ] **Step 3: Run focused verification:** PowerShell tests, backend manual-seed unit tests, Ruff, mypy, Web lint/typecheck/test/build, and `node --check`.
- [ ] **Step 4: Run actual double-click-equivalent smoke:** invoke the start CMD entry non-interactively, verify health and the four listeners/owned containers/browser pages, invoke the stop CMD entry, then verify exact project removal and four ports released.
- [ ] **Step 5: Run fresh root verification and Phase 8 risk-matched regression; inspect `git diff --check`, `git status`, runtime logs, and evidence-boundary copy before reporting.

## Plan self-review

- Spec coverage: all architecture, identity, ownership, failure recovery, documentation, and verification requirements map to Tasks 1–4.
- Placeholder scan: no deferred implementation placeholders remain.
- Interface consistency: the seed JSON fields consumed by browser and lifecycle tasks are named once and reused consistently.
- Scope: no production route, provider, automation, live observation, main-worktree file, commit, or push is included.
