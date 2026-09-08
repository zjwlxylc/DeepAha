# 调查结果的内部机会与岗位登记

实现基线：main fcd1205（PR #13）。本批接入身份登记，后续字段审核按计划另批接入。

## 行为

审核员完成内部材料审核及全部文档准备后，可选择关联已有机会，或人工填写名称、类别与发布单位登记内部机会；岗位可以同时登记，也可以在明确的归属修订上追加。单位分组保持原样，不静默登记成岗位。

新机会保持 `INTERNAL / UNKNOWN`，初始版本保持 `PENDING`；发布日期与报名截止时间不猜测，不产生 `VerifiedFact`，不公开发布。来源集合、身份、岗位及归属回执在一个数据库事务内提交；任一步失败全部回滚。

登记复用现有 Resolver、OpportunityUnitService、WMA 来源集合和通用 Reader 0.9 文档。已有身份、可能重复的标题与发布者、过期版本、重复岗位和失效审核权限拒绝写入。同一请求回放返回原回执；浏览器在请求发出前固定表单标识，回执丢失后保留填写内容与同一请求身份。

## 验证记录

- 缺失登记契约时，新增真实数据库用例收集失败；新增前端 Action 未实现时，两项行为测试失败。实现后均通过。
- API 与 Resolver 纯组件：86 passed。
- PostgreSQL 定向（身份登记、绑定、Resolver、身份变更）：51 passed，包含 13 项新增登记场景。
- 后端非集成：1298 passed / 532 deselected；Ruff 与 mypy Windows / Linux 通过（422 source files）。
- 前端：141 passed；typecheck、lint、production build 通过。
- 浏览器：桌面 1280×900、移动 390×844 共 14 passed；包含新机会登记和补充岗位的回执丢失重试。视觉检查修正岗位勾选框布局后，新登记流程 4 passed，构建再次通过，截图检查无横向溢出。
- 独立评审未发现 P2 及以上问题；独立运行 50 项 Resolver / versioning 测试、6 项身份 API 测试，以及两个 Action 的回执丢失重试检查。没有使用共享数据库或真实人工身份。
- 完整 PostgreSQL / S3 回归：529 passed / 3 skipped / 1298 deselected，422.68 秒；Alembic check 无新增迁移操作。
- 候选 `9b4b5722ae1e32f80bf687ab0e846d735965b4ac` 的 CI #82（run 34222579486）9 项全部 success；PR #14 已合并为 `757fb3c0522b2092bbaa402e3e8ea3ea166d783f`。候选与合并代码树均为 `707e8c8e7dd37b85d9cb8f58c4573b434838b570`。结构化记录见 `evidence/2026-09-08-identity-ci.json`。

测试入口：`backend/tests/integration/test_investigation_registration.py`、`backend/tests/api/test_investigations.py`、`web/tests/investigations-actions.test.ts`、`web/e2e/investigations.spec.ts`。

本地视觉证据：`web/output/playwright/investigations/investigations-registers-i-1cdc9--without-duplicate-creation-desktop/identity-retry.png` 及同名 `mobile` 目录；补充岗位截图位于 `investigations-registers-i-75d39--without-duplicate-creation-*`。这些截图使用合成数据，不代表真实独立审核。

## 未改变的事实边界

没有重新调用 WMA，没有更改 V3 Prompt、模型、冻结 Schema、Candidate Facts、原文与定位。本批不更改引文比较链；原冻结回放证据继续适用：94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED。工程接入通过不能替代独立人工核验与发布资格。
