# SG4 可计算事实与 Eligibility 实施计划

## Goal
在 SG1–SG3 已人工验收的 Root/Unit/Target/Currentness 基线上，建立独立的 Computation Lane，只消费当前、可定位、可确定性归一化的事实，安全回答“我现在能不能参加这个具体机会？”。

## Architecture
Display Lane 继续原样收录 WMA 原文；SG4 新增 `deepaha.product.eligibility` 作为计算轨。它从当前 CatalogTarget 的 own/ancestor/common fields 中提取 typed candidates，验证 Evidence locator，执行有限的确定性归一化与四态 Eligibility 聚合。任何未定位、冲突、例外、作用域不明或画像缺失都保持 UNKNOWN/UNCERTAIN；LLM 不参与最终资格落锤。

## Global constraints
- SG3 是冻结基线；不得改变 Root/Unit/Target/currentness 语义。
- INELIGIBLE 只能由“明确硬条件 + 当前 Evidence + 确定性比较”产生。
- UPDATE_PENDING 的受影响内容不得用于最终资格否定。
- WMA `CONFIRMED` 不是自动事实批准；必须通过本地 Evidence support 检查。
- 不恢复逐字段人工批准、方法认证、规则审批前置。
- SG4 不做 SG5 Value/Priority/推荐排序。
- 个人画像不发送给 WMA 或任何外部模型。

## Task 1 — Eligibility contract tests (RED)
新增 `backend/tests/product/test_eligibility.py`：
- located hard conflict → INELIGIBLE；
- same conflict unlocated → UNCERTAIN；
- all supported satisfied + unknown coverage → LIKELY_ELIGIBLE；
- explicit complete coverage + all supported satisfied → ELIGIBLE；
- missing profile/ambiguous exception/conflict source → UNCERTAIN；
- major code prefix mapping only when explicit codes exist；
- xlsx sheet/row/column locator is verified against immutable artifact；
- expired evidence-backed application deadline can produce INELIGIBLE；
- UPDATE_PENDING caps aggregate status at UNCERTAIN；
- unsupported hard condition blocks positive status but does not create INELIGIBLE。

## Task 2 — Computable fact lane
Create `backend/src/deepaha/product/eligibility.py` with:
- typed candidate extraction;
- evidence support resolver (text-located reuse + bounded XLSX cell verification);
- deterministic normalizers for education, explicit graduation year, explicit birth cutoff/age, explicit hukou region, explicit major codes, exact deadline;
- safe evaluator and four-state aggregation;
- UNKNOWN fact state vs UNCERTAIN aggregate status separation.

## Task 3 — Profile contract
Extend profile with optional:
- `birth_date` (YYYY-MM-DD)
- `major_code` (2–8 digits)
- `hukou_region`
Keep existing fields and data export/erase behavior.

## Task 4 — Product/API integration
- `PersonalMixin.fit()` delegates to SG4 evaluator;
- existing `/api/me/fit/{target}` remains stable but returns detailed criteria/evidence/coverage;
- no new approval endpoint;
- no database migration required.

## Task 5 — Mobile eligibility UX
- profile page can collect the new optional qualification attributes;
- “适合我吗” shows aggregate four-state result plus per-condition satisfied/conflict/unknown rows and Evidence locator summary;
- UI explicitly says profile data comes from user and unresolved items need checking;
- no fake score or probability.

## Task 6 — SG4 examples and Gate D evidence
Provide synthetic local examples for all four statuses and an XLSX-backed hard condition. Re-run:
- all 117 SG3 product tests;
- SG4 tests;
- frontend checks;
- `deepaha.product` compile;
- user real 106-position replay to confirm target counts/currentness unchanged.

## Gate D
PASS only if:
1. no INELIGIBLE without deterministic conflict + current official evidence;
2. missing/ambiguous/unlocated/exception conditions remain UNCERTAIN;
3. SG1/SG2/SG3 tests remain green;
4. real 106-position data stays 106 targets with original artifacts untouched.
