# 组规则与岗位只读依据页面

本批 IMPLEMENTED，本地定向检查通过；尚未写入适用裁决，不代表整个 GROUP 继承链路或发布资格完成。沿用 `codex/group-rule-applicability`，包含前批内部上下文提交 `3bd26b5`。

新增两个私有 GET：岗位的 `group-rule-contexts` 用于发现已保存记录，`group-rule-applicability/{source}/{candidate}` 返回严格 `GroupApplicabilityView`。接口复用实际 PostgreSQL 上下文重建、授权和 `private, no-store`；响应校验关联身份、摘要、实际批准、完整组审核和岗位计划。无新迁移或写入接口。

从岗位条件快照进入桌面优先的依据页，左侧官方段落和原件定位，右侧完整组字段、成员、组批准与岗位未完成项，窄屏堆叠。显示固定“尚未裁决”，没有适用批准按钮。原文最多每页 50 段；下一页上下文变化时隐藏旧内容，重新读首页。页面刷新、权限失效、过期和不可用时隐藏旧记录。空记录列表不表示没有组条件。

独立审阅发现并修复两项 P2：

- 历史准备记录阻塞新来源发现：先从冻结层级确定岗位父组，再按当前 binding、check、ACTIVE FactSet 筛选；所选记录仍严格重建。真实合成回归保存旧历史，补第二岗位绑定，重建组审核并以 supersedes 创建新岗位事实集，证明新记录可发现、旧记录拒绝。
- 第一轮快照读取成功、第二轮入口请求失权后旧内容未隐藏：入口失败即清除整个页面数据。三种后续失败用例验证旧快照不再渲染。

最终验证：15 项 PostgreSQL 集成测试、8 项 API 边界测试、26 项定向 Vitest、8 项 Playwright（新上下文 6 + 原岗位快照 2，桌面与窄屏）通过；5 个 Python 文件 Ruff/mypy、12 个前端文件 ESLint、生产构建通过。没有重复整站前端单元测试；新增路由及修改后页面需要的构建已实际执行。此前 46 项旧公告适用/岗位快照回归证据继续保留。

首次浏览器 5 通过/1 失败，原因是测试同时命中业务 alert 和 Next 隐藏路由播报；限定主内容后最终 6 项通过。截图已逐张查看，无横向溢出或遮挡。合成响应取自实际 PostgreSQL 测试，保存在 `web/tests/group-applicability-fixture.json`；不是实际人工批准。

证据：`evidence/2026-09-10-group-applicability-api-tests.xml`、`evidence/2026-09-10-group-applicability-ui-validation.json`、`evidence/2026-09-10-group-applicability-ui/{desktop,mobile}.png`。

## 下一安全恢复点

PR #33 已合并。候选 `fef6951` 的 CI #121（run `34464433277`）全部 9 个 job 成功；合并提交 `7d34810` 与候选代码树一致，证据见 `evidence/2026-09-10-group-applicability-ui-ci.json`。后续 GROUP 适用决定独立持久化在 `codex/group-applicability-decisions` 推进；该步骤完成情况见 `2026-09-10-group-applicability-decisions.md`。保持当前任务窗口与工作区，无需重跑 WMA。

真实样本仍为 94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED，整体资格 UNCERTAIN。未改 V3 Prompt、冻结 Candidate Facts、原件或证据 Gate。
