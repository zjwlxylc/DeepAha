# SG4 Final Verification

Version: `3.4.0-rc1`

## Product tests

All 11 `backend/tests/product/test_*.py` files were executed in fresh pytest processes on the final code tree.

- **134 passed**
- **0 failed**
- SG4 `test_eligibility.py`: **17 passed**
- collection cross-check: **134 tests collected**

Evidence: `product_tests_by_file.txt`.

## Web contract

`node web/scripts/check-product.mjs` → PASS.

Covers JavaScript syntax, no-fixture rule, SG1 actionable targets, SG2 multi-type presentation, SG3 currentness and SG4 eligibility/profile/evidence UI contract.

Evidence: `web_check.txt`.

## Compile

`python -m compileall -q backend/src/deepaha/product` → PASS.

Evidence: `product_compileall.txt`.

## Four-state API acceptance

Four fictional opt-in packages under `examples/sg4-eligibility/` produced exactly:

- E01 → `ELIGIBLE`
- I01 → `INELIGIBLE`
- U01 → `UNCERTAIN`
- L01 → `LIKELY_ELIGIBLE`

I01 conflicts were backed by stored XLSX cells. `llm_used=false`. New profile attributes survived personal data export.

Evidence: `api_acceptance.json`.

## Real user WMA regression

Input: a copy of the user's originally uploaded RC2 `deepaha.db + objects`.

- GROUP units: 58
- POSITION units: 106
- current Catalog Targets: 106
- second SG1 projection: idempotent, no data modification
- legacy authoritative table digests unchanged
- object store digest unchanged

Sample target: real `综合管理 / 编号1`.
Test profile: 本科 / 广告学 / 050303 / 1985-01-01.
Result: `INELIGIBLE` with evidence-backed deterministic conflicts including:

- education → saved XLSX `岗位信息表!K5` → `XLSX_CELL_MATCH`
- major code → saved XLSX `岗位信息表!M5` → `XLSX_CELL_MATCH`
- age → position age condition plus located announcement age interpretation

Evidence: `real_106_eligibility.json`.

## Safety cases

SG4 tests prove fail-closed behavior for:

- same apparent conflict with unlocated evidence;
- corrupt XLSX;
- exception / alternative wording;
- generic “应届毕业生” wording;
- nonexclusive “相关专业” semantics;
- unsupported hard conditions;
- SG3 `UPDATE_PENDING` affected fields;
- parent age explanation accidentally treated as a global child condition;
- age interpretation where either side of the supporting evidence is unlocated.

No LLM/Agent is used to emit an Eligibility verdict.

## Scope stop

SG4 is a local acceptance candidate. SG5 Opportunity Value / Priority is intentionally not implemented and must not begin before user acceptance.
