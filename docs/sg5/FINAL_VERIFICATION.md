# SG5 Final Verification

Release candidate: `3.5.0-rc1`  
Base: user-accepted `3.4.0-rc1 / SG4`

## 1. Backend product regression

Twelve `backend/tests/product/test_*.py` files were executed in explicit pytest processes. Final total:

- **147 passed**
- **0 failed**
- **12/12 files returned RC=0**

Evidence: `product_tests_by_file.txt`.

SG5-specific contract coverage consists of 12 tests in `test_personal_value.py` plus the SG5 API/profile contract in `test_api.py`.

## 2. Front-end contracts

- `node web/scripts/check-product.mjs` → PASS
- `node web/scripts/check-sg5.mjs` → `SG5_FRONTEND_CONTRACT=PASS`

The checks cover SG1 actionable UI, SG2 multi-type UI, SG3 currentness, SG4 eligibility, SG5 Top-N/value explanation, personalization controls, and absence of fake percentage claims.

Evidence: `web_checks.txt`.

## 3. Product module compilation

`python -m compileall -q backend/src/deepaha/product` → PASS.

This scope intentionally excludes historical legacy modules outside the current `deepaha.product` composition.

Evidence: `product_compileall.txt`.

## 4. Real WMA data replay supplied by the user

The uploaded `deepaha-data(1).zip` was inspected through an isolated copy; the supplied package was not modified.

Observed snapshot:

- Tasks: 9
- Result snapshots: 7
- Approved overview revisions/publications: 6
- Opportunity units: 425
- CURRENT catalog targets: **328**
  - public-institution/recruitment jobs: 300
  - competition tracks: 21
  - youth policy/benefit branches: 7

SG5 initialization produced **no database schema change** and did not modify object-store files.

Three ranking scenarios were replayed:

1. **Existing minimal profile: `宁波 + 政策`, no explicit type**  
   Candidate count 67. SG5 inferred policy only as a retrieval hint. The first 7 ranked targets are actual `YOUTH_POLICY_BENEFIT` branches, followed by exploration candidates.
2. **Explicit policy preference**  
   Candidate count 7; all candidates are the 7 policy/benefit targets.
3. **Explicit competition + AI profile**  
   Candidate count 21; all candidates are competition tracks.

`llm_used=false` in all scenarios.

Evidence: `real_wma_value_replay.json`, `real_wma_value_replay.final.log`, `REAL_WMA_DATA_ANALYSIS.md`.

## 5. Timing safety

All 328 current targets in this uploaded snapshot have `content.deadline = null` even though many field records contain deadline text. SG5 therefore does not create a precise countdown from free text. It only uses a Target canonical deadline or a SG4 `APPLICATION_DEADLINE` with `LOCATED` evidence and a normalized date.

This is an intentional fail-closed behavior.

## 6. Ranking baseline calibration

The TDD calibration fixture includes a job whose text contains `政策` plus two true policy benefits. The legacy keyword baseline is reproduced locally; SG5's top-2 precision is asserted as 1.0 and strictly higher than the keyword baseline.

This is a **curated engineering calibration**, not an independent human blind evaluation. Gate E remains pending the user's local manual acceptance.

## 7. Browser limitation

Native Chromium navigation is blocked in this execution environment by `ERR_BLOCKED_BY_ADMINISTRATOR` before the application bridge can satisfy navigation. No native-browser visual PASS is claimed here.

Static UI contracts and backend/API behavior are verified; final visual/product acceptance is intentionally left to the user's Windows reproduction.

Evidence: `browser_environment.json`.

## 8. Scope / non-claims

SG5 does not claim:

- learning-to-rank model training;
- external LLM ranking;
- success/offer probability;
- all-opportunity type coverage in the newly uploaded real WMA snapshot;
- SG6 monitoring/learning-loop completion;
- production deployment or PostgreSQL qualification.

Verdict: **SG5_LOCAL_ACCEPTANCE_CANDIDATE**.
