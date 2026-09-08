# 调查事实到独立规则审核

当前批次将已保存的 ACTIVE 审核事实集接入独立规则审核。每个公告或岗位分别整理规则候选；所有已审核事实、全部原始字段、未知项和不能执行的条件继续保留。规则决定与事实决定分开，批准单条规则不代表完整条件覆盖，也不产生资格结果、UnitRuleSet 或公开发布。

## 实现与审计边界

- 入口校验当前材料、身份归属、机会/岗位版本、来源包、事实准备、事实集及机械核验回执。缓存命中和每次决定前均重放共同核验，核验版本变化后拒绝旧请求。
- 候选复用派生器 1.0.1，使用独立 `direct-wma-rule-bridge/2.0.0+deriver-1.0.1` 版本。保留真实 UNIT 身份，提取 `compile_rule_graph` 校验规则，无虚构 Opportunity。既有 RuleSet 编译哈希保持不变。
- APPROVE 需逐条评估全部对应 EvidenceRef 的权威级别、支持或矛盾关系、有依据的带时区生效时间、精确适用目标及理由。所有决定的证据 ID 必须唯一且属于当前候选。系统不预选批准、权威、时间或适用性；不能确认时可保留待裁决。
- NEEDS_ADJUDICATION 可追加最终决定；终态不能反转。按最终决定优先显示，完整历史保留。相同请求重试不重复写入，任务行锁保护并发。
- 迁移 0041 增加不可变规则准备及决定回执，数据库校验真实文档块/位置/引用/目标和审核身份。即使重算 JSON 摘要，伪造展示证据也会被拒绝。P9-B 决定与独立调查回执需在同一事务配对提交；有历史时拒绝破坏性降级。
- 私有 API 与浏览器端延续既有访问边界。桌面审核为主，手机可浏览；所有表单保持请求身份与填写内容，过期清单只读。原始 quote、共同核验各维度、完整原文及原件下载沿用同一证据链。

## 验证记录

- 新 API 实现前 4 项失败（路由不存在），实现后定向 PostgreSQL/API 共 56 passed。包括独立决定、缺失/外来/重复证据、当前版本、未知事实、待裁决、数据库绕过及并发提交。
- 全部非集成后端测试：1344 passed / 579 deselected；Ruff、格式与 mypy Linux / Windows（431 files）通过。
- 0041 在本次专用空测试库中完成降级至 0040、升级至 head；`alembic check` 无新增操作。
- 全部前端组件测试：170 passed / 33 files；构建、类型及 lint 通过。新增规则组件与 action 共 25 项。
- 浏览器测试首轮 16 passed / 2 failed；新增测试误将祖先 region 放入表单的相对 `has` 查询，已依据页面快照修正。修正后桌面与手机全 18 项通过（59.4 秒）。规则流程三次丢失响应的 6 次 POST 只产生 3 次写入，待裁决后仍可继续，刷新后终态和历史保留。
- 全库 PostgreSQL/Moto：576 passed / 3 skipped / 1344 deselected，511.84 秒；包括有历史时降级被拒绝且历史仍可读取。后端与 API/UI 两轮独立复核无 P2+，分别独立运行 20 和 25 项纯测试通过。
- 最后将拟规则表达式补充为中文条件说明并保留原始表达式，类型、lint、构建、9 项组件测试及桌面/手机 2 项规则流程复测通过（12.7 秒）；实际检查两端截图，无横向溢出。完整机器记录与截图路径/摘要见 `evidence/2026-09-08-rule-review-validation.json`。
- 实现状态 IMPLEMENTED，已合并 PR #17。候选 `27cdd34e828f8ebbdea8eb26d595be73c7a326cc` 的 CI #88（run 34232467147）九项均通过，合并提交 `7606ce6ff0877f51667df473d375b0b8e7f3427a`；候选与合并代码树均为 `5630884a2ae0c6016a68dc97340b8b3f7434ce91`。见 `evidence/2026-09-08-rule-review-ci.json`；工程集成不等于发布资格。

## 证据和保留事项

测试入口：`backend/tests/integration/test_investigation_rules.py`、`backend/tests/investigations/test_rule_review.py`、`backend/tests/rules/test_compiler.py`、`backend/tests/api/test_investigations.py`、`web/tests/investigation-rule-review.test.tsx`、`web/tests/investigation-rule-actions.test.ts`、`web/e2e/investigations.spec.ts`。

冻结样本复用 `evidence/2026-09-08-field-review-receipt-replay.json` 的同一共同核验实现与输入证据：124 条中 94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery 仍 UNVERIFIED；本批未调用 WMA、未下载官方材料、未改动 Prompt、Schema、原件或 Candidate Facts。本批所有人工身份、证据评估和浏览器写入均为合成测试，不代替真实独立人工签署或发布资格。

下一批才处理精确岗位资格：共同条件适用、例外、冲突、未接入条件及时间语义必须进入显式覆盖审查。单条规则审核或编译通过不能被用作完整资格证明。
