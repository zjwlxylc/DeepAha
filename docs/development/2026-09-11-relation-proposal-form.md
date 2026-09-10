# 从跨层级条件总览新建关系提案

总览的有效当前预览提供新建入口，桌面表单按完整 manifest 顺序选择至少两个跨层级条件，展示层级、原始值、状态与适用范围。默认 UNRESOLVED；累积、例外、冲突遵守现有 RelationProposal 的状态与证据覆盖规则。EXCEPTION 必须明确非空、非全部的替代子集。逐字引文不 trim、不做语义近似替换；条件证据可以绑定所选子集，关系证据绑定全部所选条件。

新增私有只读 relation-proposal-context 适配，复用当前来源构建、真人权限、绑定原文块与读取后重查，返回 Python 生成的完整 review_hash，原文块按 50 条分页。前端不重算包含原始浮点的完整 review 摘要。提交前从当前服务取得摘要并比较原请求，薄请求不携带 producer_id、source_review 或 bound evidence；后端仍执行全部验证。保存回执核对任务、岗位、请求字段、证据与安全状态后跳转已有稳定详情地址。

重复点击由同步锁拦截，未知回执保留同请求和 nonce 重试；失败隐藏旧条件。读取失败不删除原重试请求，来源变化拒绝写入，重新读取成功清空草稿。页面按任务/岗位重新挂载，避免跨路由复用旧状态。提案只追加，不允许自审，executable=false、资格 UNCERTAIN 保持不变。

## 验证证据

- 定向前端 15 项：9 项新表单/action 检查与原条件总览 6 项回归，含例外子集、逐字引用、覆盖、来源变化分页、错误回执、同请求重试。见 evidence/2026-09-11-proposal-form-unit.xml。
- 真实 PostgreSQL/API 普通与原始 locator 含 1.0 两组往返通过；包含可信摘要、分页游标、错误任务、创建、独立审核及刷新。见 evidence/2026-09-11-proposal-context.xml；本轮合成导出为 web/tests/relation-proposal-fixture.json。
- 新读取入口三项关闭入口/无关角色/未登录测试通过，见 evidence/2026-09-11-proposal-context-gates.xml。
- 桌面 Playwright 两项通过（16.1 秒）：从总览填表保存、等待 URL 后刷新恢复详情，以及原审核/STale 回归。使用真实 PG 导出的合成回执模拟 API，不是浏览器连接真人生产服务。截图 evidence/2026-09-11-proposal-form.png 已由图像工具检查。
- 受影响文件 ESLint、TypeScript、Ruff、mypy 通过；未重复本地整站测试和生产构建。浏览器测试复用现有 CI 入口。

前序 PR #45 的精确候选 700ef4ed41898c492f09101035679c6aa1affd86 已九项 CI 成功并合并为 fa4ce2295b0add94c828333b860083843dc6b971，代码树相同；见 evidence/2026-09-11-relation-index-ci.json。

本轮没有调用 WMA、修改原始证据或 Evidence Gate；工程测试不构成真人独立裁决或发布资格。历史指数格式 locator 的冻结迁移问题不在本批范围内。
