# DeepAha SG7.1 自测报告

结论：**SG7_1_ENGINEERING_SELF_TEST=PASS**；当前为 **SG7_1_LOCAL_USER_ACCEPTANCE_CANDIDATE**。

## 核心修正验证

- Digital Twin V2：100 个；组合覆盖修正；
- Eligibility 独立 Oracle：6×100=600，600/600，accuracy=1.0；
- Recommendation 独立 Oracle：20×100=2000，2000/2000，accuracy=1.0；
- 推荐混淆：FEATURE→FEATURE 371，HOLD→HOLD 1629，mismatch=0；
- unsafe recommendations = 0；
- engineering truth 与 independent human Gold 分开，real_gold=0；
- WMA/LLM 未用于 Oracle；
- production mutation=false。

## 回归

- 28 product test files；
- 219 tests；
- 28/28 files RC=0；
- Python compileall PASS；
- product / SG5 / SG5.1 / SG6 / SG6.1 / SG7 / SG7.1 前端合同 PASS。

## 真实 HTTP

- 3.7.1-rc1 启动 PASS；
- Cookie+CSRF 登录 PASS；
- V2 100 Twins PASS；
- Gold Smoke 100 Pair / unsafe=0；
- 无真值时 accuracy=null，不假绿；
- Founding join/leave PASS；
- Catalog 实验前后数量不变。

## 安全边界

- 不包含用户数据库；
- 不包含用户对象存储；
- 不包含 WMA API Key/Agent ID；
- 本轮未额外触发 WMA 调查；
- Lab 不可写生产事实/审核/规则/正式 Eligibility/Ranking。

详细证据见 `docs/sg7_1/03_VALIDATION.md` 与 `evidence/sg7_1/`。
