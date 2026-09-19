# SG5.1 Final Verification

Candidate: `DeepAha 3.5.1-rc1 / SG5.1`

## Product tests

Final test tree contains **161 product tests across 14 files**. Each file was executed in a fresh pytest process and returned `RC=0` after the last production-code change.

| File | Tests | Result |
|---|---:|---|
| test_actionable_granularity.py | 13 | PASS |
| test_api.py | 6 | PASS |
| test_contract.py | 21 | PASS |
| test_currentness.py | 12 | PASS |
| test_currentness_api.py | 2 | PASS |
| test_delivery_quality.py | 13 | PASS |
| test_eligibility.py | 17 | PASS |
| test_milestones_management.py | 12 | PASS |
| test_multitype_opportunity_core.py | 10 | PASS |
| test_operations.py | 9 | PASS |
| test_personal_value.py | 12 | PASS |
| test_scout_import.py | 29 | PASS |
| test_sg5_1_frontend_contract.py | 2 | PASS |
| test_worker.py | 3 | PASS |

`TOTAL = 161 / 161`.

## Static verification

- `node --check web/public/product/*.js` → PASS
- `python -m compileall -q backend/src/deepaha/product` → PASS

## Regression found and closed during final verification

SG2 already had a safety test where the child field value is `2099-08-18` but the located Evidence quote contains a different date. Initial SG5.1 logic incorrectly treated `located=true` alone as sufficient and promoted the unsupported child value.

SG5.1 was tightened so a computable milestone now requires both:

1. Evidence can be re-located in immutable source material; and
2. the located Evidence quote actually contains/supports the normalized date/time point.

The SG2 regression test and the full milestone suite are green after the fix.

A second regression test verifies that `报名方式 / 申请方式 / 报名上限` without temporal content do not create false milestone noise.

## Real WMA data replay

Source: copy of the user's previously uploaded WMA data directory. The source database and source object store were never modified.

First SG5.1 upgrade:

- current targets: **328**
- roots: **6**
- targets with safe application deadline: **282**
- `READY`: **282**
- `PARTIAL`: **46**
- action state `OPEN`: **68**
- action state `CLOSED`: **214**
- action state `UNKNOWN`: **46**
- backup created and verified before projection refresh

Second SG5.1 upgrade:

- `already_current=true`
- `data_modified=false`
- no second backup created

Interpretation: approximately 86% of current targets recovered a safe application deadline from WMA-read content **without** trusting unlocated date strings. The remaining 46 stay unresolved because current Evidence/currentness is not sufficient to support a primary application deadline.

## Data-integrity verification

Unchanged before vs after SG5.1 replay:

- `product_opportunity_identity`
- `product_opportunity_units`
- `product_overview_decisions`
- `product_overview_publications`
- `product_overview_revisions`
- `product_result_snapshots`
- `product_tasks`
- every file under the copied `objects` directory (aggregate SHA-256 map unchanged)

SG5.1 changes only the derived CatalogTarget JSON time projection and product metadata needed to record the projection version.

See `REAL_WMA_TIME_VALIDATION.json` for machine-readable evidence.

## UI / interaction proof

Because native Chromium navigation is blocked by administrator policy in this environment, SG5.1 uses the same explicit test HTTP bridge approach as earlier accepted stages. Real static JS/CSS is loaded into Chromium; every business request is forwarded to the real FastAPI application and the copied user SQLite database. This does **not** certify native cookies, CSP or networking.

Checks passed:

1. grouped catalog management on real 328-target data;
2. expand one parent root to concrete targets;
3. secondary exact-target view preserves precise withdrawal action;
4. public catalog renders safe time semantics;
5. no whole-page horizontal overflow at 1280 / 1440 / 1920;
6. page errors: 0.

Screenshots:

- `screenshots/01_grouped_catalog_real_data.png`
- `screenshots/02_group_expanded.png`
- `screenshots/03_exact_target_view.png`
- `screenshots/04_public_safe_times.png`

## Boundary

SG5.1 does not enter SG6. It does not change WMA prompts, add a second fact store, introduce per-field human date approval, infer uncertain dates into deadlines, or add learning/notification behavior beyond using already-safe deadlines in existing SG5 `Why now` and existing reminder mechanisms.
