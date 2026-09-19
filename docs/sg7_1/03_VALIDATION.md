# SG7.1 最终验证记录

## 1. 独立标准答案

证据：`evidence/sg7_1/independent_gold_oracle_final.txt`

### Eligibility

- 6 cases × 100 twins = 600 pairs；
- truth_pairs = 600；
- truth_accuracy = 1.0；
- unsafe_recommendations = 0；
- real_gold_pairs = 0；
- llm_used = false；
- production_mutated = false。

### Recommendation

- 20 cases × 100 twins = 2000 pairs；
- expected FEATURE = 371；
- expected HOLD = 1629；
- recommendation_accuracy = 1.0；
- confusion = FEATURE→FEATURE 371 / HOLD→HOLD 1629；
- mismatch = 0；
- unsafe_recommendations = 0；
- real_recommendation_gold_pairs = 0；
- llm_used = false；
- production_mutated = false。

## 2. 全产品回归

- `backend/tests/product/test_*.py`：28 files；
- collected：219 tests；
- 28/28 files 独立 pytest process `RC=0`；
- failed files = 0。

证据：

- `evidence/sg7_1/product_regression_final.json`
- `evidence/sg7_1/final_product_files/`

整套 pytest 单进程在当前容器仍存在项目既有的长进程退出/挂起现象，因此最终 Gate 使用“每测试文件独立进程 RC=0”，避免把显示 passed 与真实退出码混淆。

## 3. 静态和前端

PASS：

- `python -m compileall -q backend/src backend/tests/product tools/source_asset_importer`；
- Node syntax：lab-ui / workbench / user；
- `check-product.mjs`；
- SG5；
- SG5.1；
- SG6；
- SG6.1；
- SG7；
- SG7.1。

证据：`evidence/sg7_1/static_and_frontend_checks.txt`。

## 4. 真实 HTTP Smoke

使用隔离 SQLite 数据目录启动真实 HTTP 服务：

- `/health/live` = 3.7.1-rc1；
- Cookie + CSRF 登录 PASS；
- V2 Twin：100；
- Gold Benchmark：1 case × 100 twins = 100 pairs；
- 无 Pair Truth 时 truth_accuracy 保持 null，不假绿；
- unsafe_recommendations = 0；
- `llm_used=false`；
- `production_mutated=false`；
- Founding User：NOT_JOINED → ACTIVE → WITHDRAWN PASS；
- 正式 Catalog 数量实验前后相同。

证据：`evidence/sg7_1/http_smoke_final.json`。

## 5. 升级

测试覆盖：

- SG6.2 → SG7.1 新建实验层；
- SG7 V1 → SG7.1 V2；
- backup-first；
- V1 Twins 仅 inactive，历史保留；
- V2 重新生成 100；
- 正式 authority counts / objects 不变化；
- 第二次升级幂等。

## 6. WMA

SG7.1 没有修改 Direct WMA 协议，也不需要 WMA 参与 Gold Benchmark/Oracle。用户提供的 Agent ID/API Key 未写入源码、测试证据或交付 ZIP。本轮没有为了 SG7.1 额外发起付费调查调用。

## 7. Verdict

**SG7_1_ENGINEERING_SELF_TEST=PASS**

当前发布状态：**SG7_1_LOCAL_USER_ACCEPTANCE_CANDIDATE**。

独立人工 Gold 和 Founding User 真人价值实验仍未被工程 Oracle 替代。
