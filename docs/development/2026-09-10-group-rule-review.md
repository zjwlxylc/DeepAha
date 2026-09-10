# 单位组规则候选与独立审核后端

状态 IMPLEMENTED，本地定向验证通过；PR #31 候选 `0ef178d` 的 CI #117 全部 9 项通过，合并为 `d5f4f7`，候选与合并代码树一致。精确回执见 `evidence/2026-09-10-group-rule-review-ci.json`。不代表发布资格或实际人工验收通过。分支 `codex/group-rule-review` 基于 PR #30 同树合并后的 `8128fbf537984f792f2800fc6660da5aa93a7ef5`。

## 已实现的范围

从当前有效的 GROUP 正式事实集生成规则候选，并分别保存独立规则审核及逐证据评估。完整保留只读预览、原始字段分母、其他层级排除项、拒绝、未知、冲突、未处理和不可执行字段。只有 KNOWN 且 deriver 1.0.1 能确定推导的字段生成 P9B RuleCandidate；候选内容保持预览一致，精确绑定 GROUP 版本、事实集、单条事实和全部引用。

本批不生成 UnitRuleSet，不激活资格规则，不处理 GROUP 到 POSITION 的继承或适用裁决。批准表示规则候选完成该范围审核，不能解释为岗位完整资格已经放行。

私有 API 均位于 `/api/v1/local-human-test/investigations`，要求有效真人审核权限，响应 `private, no-store`：

- `POST /{task_id}/group-facts/{preparation_id}/rules`：以 expected_preview_hash 保存候选；事实准备、事实集与编译版本决定稳定幂等结果。
- `GET /{task_id}/group-rules/{preparation_id}`：重新核验当前来源、原件、组身份、实际物化和审核回执后读取。
- `POST /{task_id}/group-rules/{preparation_id}/decisions`：要求 Idempotency-Key 和 expected_preparation_hash；APPROVE、REJECT 或 NEEDS_ADJUDICATION。最终决定不可重复覆盖，待裁决可追加最终决定。

新契约为 `group-rule-review/1.0.0+deriver-1.0.1`，不修改 WMA 的冻结交付 Schema。审核历史和当前决定均有强类型响应。APPROVE 要求完整引用集及每条 authority、relation、effective_at、精确适用说明；写入与读取都使用原规则构建器、编译器核验可重放性。

迁移 `20260910_0048` 添加不可变准备与决定回执。数据库核对候选实际关联的事实、证据、目标、payload、版本和摘要；延迟约束要求候选及批准拥有配对回执，阻止直接追加候选事实或证据改变物化结果。审核记录存在时拒绝破坏性降级。原只读预览仅提取可复用的同事务 helper，对外响应保持一致。

## 验证依据

最终 111 个不同测试通过，无失败、错误或跳过：

- PostgreSQL 90：新审核 26、迁移与 SQL/Python 推导一致性 21、原组预览 19、原调查规则审核 24。
- API/组件 21：新审核 API 9、原预览 API 9、P9B rule promotion 3。
- 9 个相关文件 Ruff lint/format 通过；7 个入口文件 Mypy 通过；迁移往返和 Alembic model check 通过。

命令在 `backend` 中运行，使用隔离合成 PostgreSQL 测试库：

```powershell
.venv/Scripts/python.exe -m pytest -m integration tests/integration/test_group_rule_review.py tests/integration/test_group_rule_review_migration.py tests/integration/test_group_rule_preview.py tests/integration/test_investigation_rules.py --junitxml=../docs/development/evidence/2026-09-10-group-rule-review-pg.xml -q --tb=short
.venv/Scripts/python.exe -m pytest tests/api/test_group_rule_review.py tests/api/test_group_rule_preview.py tests/p9b/test_rule_promotion.py --junitxml=../docs/development/evidence/2026-09-10-group-rule-review-unit.xml -q --tb=short
```

并发调用证明相同准备及相同审批键只产生一份回执；权限撤销、组版本变化、错误任务与时钟倒退在缓存读取/重试时仍拒绝。数据库负例包括重算摘要后篡改候选、目标、payload、引用和字段分母，无回执直接批准、追加候选子关系以及不完整证据评估。

独立只读评审发现特殊时间 `-infinity` 可被 PostgreSQL 接受，已先复现再修复；无时区日期也被负例覆盖。SQL 现在要求有限的带时区 ISO 时间，读取重新按请求契约解析并重建批准规则。推导一致性测试同时发现 tab/NBSP 全空白被 SQL btrim 与 Python strip 不同处理，改为显式 Unicode 空白集后通过。未改写实际值。末轮独立评审未发现剩余 P1/P2。

本批没有前端变更，未重复整站前端测试或生产构建。账号与证据均为合成测试，不是实际真人批准。未调用 WMA、未下载官方原件、未改 V3 Prompt、CandidateFacts、原始引文或定位。既有真实样本保持 94 PASS / 0 FAIL / 30 Word UNVERIFIED；Delivery UNVERIFIED，整体资格 UNCERTAIN。

## 安全恢复与下一步

本批 CI 与同树合并已完成。桌面优先的组规则审核表单接入见 `2026-09-10-group-rule-review-ui.md`：沿用固定地址、当前事实核验、逐引用评估、显式提交、幂等键、保存后地址确认和过期后隐藏旧结果。保留完整字段分母，不增加自动批准或岗位继承。

下一批主要是按已定后端契约接入现有页面，可在此安全节点由用户切到“中”档继续；这是依据任务边界的判断，不是已经测得 token 节省比例。无需换任务窗口。若 CI 暴露跨层或并发问题，先修复，再评估是否需要高档处理。
