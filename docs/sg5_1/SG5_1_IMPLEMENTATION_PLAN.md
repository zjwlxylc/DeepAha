# SG5.1 Implementation Plan

## Task 1 — Milestone normalization core
RED tests cover: confirmed located range -> open/deadline; exact registration_deadline; rolling; month precision; unlocated/UNKNOWN; conflict; submission deadline not replacing registration deadline; SG3 pending field.

## Task 2 — Projection/backfill
New publications materialize milestones immediately. Existing SG5 current targets receive a backup-first, idempotent JSON projection refresh without schema change or WMA rerun.

## Task 3 — API and management aggregation
Add reviewer-only catalog management summary/groups endpoints and extend catalog cards/detail with time_readiness/milestones.

## Task 4 — Workbench redesign
Default review/catalog to parent-announcement groups with metrics, filters, expandable concrete targets, and a secondary exact-target view.

## Task 5 — Regression and real-data evidence
Run SG1-SG5 tests, front-end contracts, product compile, and replay the uploaded 328-target dataset. Verify original authority tables/object bytes are not rewritten.
