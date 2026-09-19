# DeepAha 3.7.1-rc1 / SG7.1

基线：**3.7.0-rc1 / SG7**。本修正版不改变 SG1–SG6.2 正式业务语义，只收紧 Opportunity Lab 的数字分身覆盖与 Gold Benchmark 判卷可信度。

## 核心修正

1. **Synthetic Twin V2**
   - 仍为确定性 100 个合成青年；
   - 修正 V1 中学历与毕业年份使用同一周期导致的组合相关性；
   - V2 使用交叉组合，使本科×2027、本科×2028、硕士×2027等关键组合真实出现；
   - V1 Twin/Pair Truth/历史 Run 保留，但升级后退出当前 active benchmark 集。

2. **Gold Benchmark 对齐正式推荐候选 Gate**
   - 先执行用户显式 `opportunity_types` 硬过滤；
   - `STRICT` 地区偏好执行明确异地过滤；
   - 只有候选通过正式前置 Gate 后才进入 SG4 Eligibility + SG5 Value/Priority；
   - 被正式推荐链排除的 Pair 在实验中记为 `HOLD / NOT_RECOMMENDED`，不再被直接送入 Value 后误计为 FEATURE。

3. **独立确定性标准答案 Oracle**
   - 标准答案生成器不调用 WMA/LLM；
   - 不调用 `eligibility.evaluate()`；
   - 不调用 `value.assess()`；
   - 先冻结 fixture 条件和标准答案，再让正式 SG7.1 程序答题；
   - 工程 Gold 与 `INDEPENDENT_HUMAN_GOLD` 继续严格分开，不能冒充真人验证。

4. **实验层逻辑版本 V2**
   - `opportunity_lab_schema_version` 升为 `2`；
   - 从 3.7.0 升级时 backup-first；
   - 旧 V1 Twin 仅退出 active 集，不删除历史 Pair Truth/Run；
   - 不重新调用 WMA，不修改正式 Opportunity/Publication/Eligibility/Ranking/Action。

5. **历史 Python 语法清理**
   - 全仓 `compileall` 暴露 11 处旧式多异常 `except A, B:`；
   - 仅机械修正为 `except (A, B):`，不改变业务语义。

## 独立标准答案成绩

### Eligibility Oracle

- 6 道固定规则题；
- 100 Synthetic Twins；
- 600 Pair；
- 600/600 正确；
- accuracy = 1.0；
- unsafe recommendations = 0。

标准题包括：本科门槛、硕士门槛、本科+2027届、已过期机会、专业代码缺失、带放宽例外的学历条件。

### Recommendation Oracle

- 20 道固定推荐题；
- 100 Synthetic Twins；
- 2000 Pair；
- FEATURE 371；HOLD 1629；
- 2000/2000 正确；
- accuracy = 1.0；
- confusion：FEATURE→FEATURE 371，HOLD→HOLD 1629；
- unsafe recommendations = 0。

这只是**确定性工程标准答案**，不能替代独立人工 Gold 和真人 Founding User 行为反馈。

## 最终工程验证

- 28 个 `backend/tests/product/test_*.py` 文件；
- 219 tests collected；
- 28/28 文件独立进程 RC=0；
- Python `compileall` PASS；
- product / SG5 / SG5.1 / SG6 / SG6.1 / SG7 / SG7.1 前端契约 PASS；
- 实际 HTTP 3.7.1-rc1 启动与登录 PASS；
- V2 100 Twins PASS；
- HTTP Gold Smoke 100 Pair、unsafe=0、无假准确率；
- Founding User join/leave PASS；
- Catalog 数量实验前后不变；
- `llm_used=false`；
- `production_mutated=false`。

当前状态：**SG7.1_ENGINEERING_SELF_TEST=PASS / Windows 本地人工验收候选**。
