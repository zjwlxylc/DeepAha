# SG3 Final Verification

Version: `3.3.0-rc1`

## Automated product tests

- 10 `backend/tests/product/test_*.py` files executed in separate fresh pytest processes.
- Total assertions/tests: **117**.
- Failures: **0**.
- Every file returned exit code 0.
- Evidence: `product_tests_by_file.txt`.

SG3-specific files:

- `test_currentness.py`: 12 passed.
- `test_currentness_api.py`: 2 passed.
- SG3-specific total: **14 passed**.

## Web product contract

`node web/scripts/check-product.mjs` → PASS.

Covers SG1 actionable UI, SG2 multi-type UI, SG3 currentness UI, syntax, and no-fixture rules.

## Compile

`python -m compileall -q backend/src/deepaha/product` → PASS.

Whole historical `backend/src` compileall is not an SG3 gate because deprecated/inactive legacy modules inherited from older project code contain pre-existing Python2-style multi-exception syntax.

## Real user-data regression

Input basis: a copy of the user's originally uploaded RC2 WMA data (`deepaha.db + objects`).

Fresh SG1 projection with final SG3 code:

- GROUP: 58
- POSITION: 106
- Catalog targets: 106
- second upgrade: `already_current=true`, `data_modified=false`
- legacy authoritative table digests unchanged: true
- object tree digest unchanged: true

Evidence: `real_sg1_regression.json`.

## SG3 API scenario

Fictional A01/A02 flow verifies:

- only A01 becomes pending when A01 deadline changes;
- A02 remains current;
- only A01 old deadline reminder is cancelled;
- target-specific RECHECK instruction excludes A02;
- approval changes A01 deadline 2026-11-10 → 2026-12-05;
- history and compare preserve before/after;
- manual withdrawal of A01 leaves A02 current.

Evidence: `api_acceptance.json`.

## Browser environment

Native Chromium HTTP navigation is blocked by administrator policy (`ERR_BLOCKED_BY_ADMINISTRATOR`) before the application can be exercised. SG3 therefore does **not** claim native browser acceptance in this container. Final visual/Windows behavior is intentionally left to user local acceptance.

Evidence: `browser_environment.json`.

## Scope stop

SG3 is a local acceptance candidate only. SG4 Eligibility is not implemented in this package and must not start before user acceptance.
