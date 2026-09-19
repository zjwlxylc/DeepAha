# SG6.1 Final Verification

Release: **3.6.1-rc1**  
Scope: desktop navigation, role entry, three-round end-to-end UI/UX closeout only. SG1–SG6 business semantics are frozen.

## Backend business regression

All 18 `backend/tests/product/test_*.py` files were executed in isolated pytest processes on the final source tree. No assertion failure was observed; the accumulated suite remains **176 passed / 0 failed**.

The container/test harness retains the same historical teardown issue seen in SG1–SG6: a long shell invocation can remain alive after pytest has printed a successful result. Therefore this release does **not** claim that one monolithic pytest command exits cleanly in this environment. Files were isolated so business failures are not confused with harness teardown.

## Frontend contracts

Final source tree:

- `check-product.mjs`: PASS
- `check-sg5.mjs`: PASS
- `check-sg5-1.mjs`: PASS
- `check-sg6.mjs`: PASS
- `check-sg6-1.mjs`: PASS
- all `web/public/product/*.js` `node --check`: PASS
- `python -m compileall backend/src/deepaha/product`: PASS

## Role UI acceptance

`evidence/sg6_1/role_ui_acceptance.json`:

- user-only has no workspace entry;
- reviewer-only label is `审核工作台` and only `内容审核` group is shown;
- operator-only label is `系统管理` and reviewer navigation is absent;
- combined reviewer+operator label is `工作台` and both groups are shown;
- workbench has no page-level horizontal overflow at 768/1024/1440/1920;
- page errors: 0.

## Responsive and basic accessibility acceptance

`evidence/sg6_1/responsive_a11y_acceptance.json`:

- user desktop/tablet 768/1024/1440/1920: no page-level horizontal overflow;
- user mobile 360/390/430: desktop nav hidden, bottom nav visible;
- mobile nav targets >=44px;
- skip link is focusable and becomes visible;
- `prefers-reduced-motion` is honored;
- active route exposes `aria-current=page`;
- page errors: 0.

## Real-data visual evidence

The earlier explicit HTTP bridge run against a **copy of the user's multi-WMA data** completed the real user-page portion before the known TestClient teardown timeout and produced:

- `screenshots/01_star_desktop.png`: desktop opportunity star with `收藏与行动` and action summary;
- `screenshots/02_actions_desktop.png`: desktop action page;

Role workbench screenshots were produced by frontend-only role acceptance:

- `04_reviewer_workspace.png`
- `05_operator_workspace.png`
- `06_owner_workspace.png`

The full bridge script later timed out in TestClient teardown and is **not** represented as a complete PASS.

## Business/data boundary

SG6.1 adds no database migration, does not rerun WMA, and does not change Currentness, Eligibility, Value/Priority, Milestone, action/feedback or reviewer/operator backend authorization semantics.

## User gate

Windows/native-browser product acceptance remains pending. Do not enter SG7 until the user explicitly accepts SG6.1.
