# S1 Implementation Plan

Goal: Implement subscription entitlements and source-contribution intake without changing the existing fact core.
Architecture: additive Python package + same-origin static UI + Product adapter + strict baseline assembler.
Tech Stack: Python 3.11+, SQLAlchemy 2, FastAPI, native HTML/CSS/JS; pytest/httpx/Playwright for checks.
Spec: 01_PRODUCT_DESIGN.md. Execution: inline, authorized by user.

## Global Constraints
No remote writes/deployment/payment/WMA calls. Preserve free catalog and current review core. Operator inherits reviewer. Snapshot existing orders. Explicit migrations only. Original R2 bytes unavailable: no complete-system claim.

## Review Focus
Different idempotency payloads; Jan31/leap day; expiry at exact end; another user guessing record IDs; network job response lost after core task creation. Tests cover all five.

## Task 1: period/security foundations and persistence
Create src/deepaha_membership/{periods,urls,db,errors}.py; tests/test_foundations.py.
RED: pytest tests/test_foundations.py -q. Expected: tests fail on missing callable implementation.
GREEN: implement aware UTC timestamps, Shanghai calendar arithmetic, URL canonicalization, schema/transaction lock, explicit initialization. Re-run same command.

## Task 2: commercial terms and grants
Create commerce.py and contracts.py; tests/test_commerce.py.
Interfaces: Store.write/read; Commerce.create_plan/update_plan/create_order/quote/confirm/grants/entitlements.
Test price snapshots, stale version409, zero/negative/noninteger rejection, trial/manual distinction, immutable grant, idempotency conflict, back-to-back renewal, archived plans, owner isolation. Execute pytest tests/test_commerce.py -q after each slice.

## Task 3: contributions and watches
Create contributions.py, watches.py, integration.py; tests/test_workflows.py.
Interfaces: canonicalize_url; Commerce.entitlements; Product.add_source/create_task/task_detail/catalog. Normalize one lead to many private submissions. Reviewer approval is metadata only. Operator dispatch requires public DNS and current entitlement. Stable core request key on retries. Test all status transitions, quotas, rate limit, failed dispatch and expired grants.

## Task 4: HTTP and responsive interfaces
Create api.py, demo.py, static/index.html, static/app.js, static/style.css; tests/test_api.py and tools/browser_check.py.
Same-origin endpoint family /api/membership; UI /membership/. Production auth reuses Product.authenticate and .auth.has_role. Demo is explicitly separate and loopback-only with generated credentials. Test unauthorized read/write, CSRF, roles, errors, UI forms and no mobile overflow.

## Task 5: assembly, documentation and verification
Create tools/assemble_r2.py and tools/verify_package.py. Exact original ZIP SHA256 required; reject alternate baseline, unsafe ZIP paths, symlinks, collisions. Copy extension into backend/src and inject mount call at one validated AST/anchor location; no destructive in-place change. Result is an UNVERIFIED integration candidate until original R2 tests run.
Run full pytest, JS syntax, browser checks, compileall. Create file-hash manifest, ZIP CRC, reextract and rerun tests. Record actual outcomes and unrun gates in TEST_REPORT.md and package receipt.
