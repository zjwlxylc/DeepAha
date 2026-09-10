# 私有组条件范围预览接口与页面

本批 IMPLEMENTED，本地定向验证通过，独立复核无剩余 P1/P2；本批精确候选 CI 待检查。前置 PR #36 的 CI #127 全部 9 个任务成功，已合并为 `48f6d8b`，候选与合并树相同。

私有 GET `/{task}/unit-plans/{plan}/group-inheritance-preview` 复用实际只读重建服务及审核授权，响应 `private, no-store`。严格响应校验完整基础快照、组来源和成员、冻结组条件分母、原字段/值/证据投影、规则对应和适用历史。仅序列化边界验证时间字符串但保持原表示，避免将旧 `+00:00` 改写为 `Z` 后破坏摘要。没有迁移、保存操作或资格编译器变更。

岗位条件快照页增加入口，地址为 `/review/investigations/{task}/unit-plans/{plan}/group-inheritance`。桌面左侧原条件及原件入口，右侧适用决定和理由；窄屏堆叠。展示全部继承、不适用和待处理条件，明确“范围预览，非资格结论”，整体资格仍为 UNCERTAIN。重读立即隐藏旧内容，失败后只保留错误与重试。相同地址的服务端重渲染按完整响应重新挂载组件，防止成功→撤权/过期或新摘要仍保留旧状态。

独立审阅复现并修复：重新计算摘要后伪造 raw_value/字段/引用、删除全部组条件，以及相同地址刷新保留旧状态。兼容性正例覆盖合法缺少 unit_level、evidence、locator，及历史 materialized original 未含 note、原件仍保留备注。仅比较时使用已存在的可选项默认值；已有非空定位或已有 note 被改写仍拒绝。冻结 Candidate Facts、原件、引用与摘要没有被改写。

验证：14 项 API／契约测试、1 项实际 PostgreSQL API 往返、25 项定向 Vitest 通过；Ruff 格式/检查、mypy、TypeScript、ESLint 和生产构建通过。浏览器桌面与窄屏共 6 项通过，最终兼容性调整后两端地址刷新/过期断言再次通过。截图已检查，无横向溢出。没有重跑整站单元测试。

证据：`evidence/2026-09-10-group-inheritance-api.xml`、`evidence/2026-09-10-group-inheritance-review-ui-validation.json`、`evidence/2026-09-10-group-inheritance-review-ui/{desktop,mobile}.png`。浏览器输入 `web/tests/group-inheritance-fixture.json` 是隔离 PostgreSQL 测试生成的合成结果，不是真实调查或人工验收。

## 下一步与恢复点

沿用当前工作区和任务。先检查本批精确候选 CI，全部成功后再合并和核对树。下一项回到公告→组→岗位之间的继承、例外和冲突计划设计；需先固定独立的可回放契约，再考虑持久化及执行，不得把本页 INHERIT 当作已满足岗位资格。这一步重新涉及跨层级语义、版本与资格不变量，适合高档；在设计前安全暂停供用户调整。

2026-09-10 用户收到账号免费 Actions 分钟耗尽通知。实时仓库元数据表明 `zjwlxylc/DeepAha` 为 public，当前 CI 使用标准 ubuntu-latest，按 GitHub 官方规则不消耗账号免费分钟；不能把通知归因于本项目当前标准 CI。账号账单来源和付费预算未读取、未修改。工作流中完整集成测试重复、前端构建重复仍是后续效率优化候选，但不是耗尽原因的证据。

真实样本基线不变：124 = 94 PASS / 0 FAIL / 30 Word UNVERIFIED；Delivery UNVERIFIED，资格 UNCERTAIN。本批没有 WMA、LLM、官方下载、V3 Prompt 或 Evidence Gate 改动。
