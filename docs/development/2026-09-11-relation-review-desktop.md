# 已保存提案的桌面审核入口

跨层级条件总览新增已保存提案入口。岗位列表从数据库读取，详情使用 `relations?proposal=<id>` 稳定地址，刷新后重新读取当前回放。页面展示所选条件及来源层级、例外替代对象、提案理由、逐字引文、官方回链、可展开的完整 locator、独立审核历史。

审核表单只追加记录，使用稳定 proposal_payload_sha256 与最新前驱；服务端 action 在 POST 前核对任务/岗位归属，回执再次核对请求和历史。失败先隐藏旧内容，允许用同请求/nonce 重试；来源失效时保留明确标记的历史并移除审核控件。UNRESOLVED 的批准选项禁用，后端仍负责权限、自审、证据及完整契约校验。审核不改变资格 UNCERTAIN。

本批仅完成“已保存提案”的导航和审核，尚不含新建提案表单，不宣称整套关系编辑流程完成。下一步在当前条件总览接选取条件、逐字证据与提案创建表单。没有调用 WMA 或修改旧证据 Gate。

## 验证

- 实际 PostgreSQL/API 导出的合成回执：`web/tests/relation-review-fixture.json`，生成测试通过（22.85 秒）；证据 `evidence/2026-09-11-relation-ui-export.xml`。
- 7 项 action/组件定向测试通过，含真实回执兼容、错误任务/岗位、请求关联、失败重读后保留原请求重试、STALE 移除控件。证据 `evidence/2026-09-11-relation-ui-unit.xml`。另跨层级原页面 6 项回归通过。
- 桌面 Playwright 稳定 URL、刷新、追加审核、再次刷新、STALE 回放与无横向溢出通过（10.2 秒）。使用隔离 dev 预览及实际 PG 导出的合成响应；不代表真人验收。截图 `evidence/2026-09-11-relation-desktop-stale.png` 已人工式视觉检查。浏览器回归已加入 CI。
- ESLint、TypeScript 类型检查通过。未重复本地整站测试或生产构建。
- 独立只读代码评审发现一次异常恢复问题（写失败后重读失败会丢失重试按钮），已修复并补回归；未发现其他 P1/P2。评审者未运行数据库或浏览器。

PR #43 与 #44 的精确候选均九项 CI 成功后顺序合并。分别为 fce502f4ae0b3b628c610ccb9a581ff1cb923b6d、f67114af91b3f742a2ae874ef7c4c11bb99f1165，合并 tree 与受测候选一致；证据见同目录 evidence 的 relation-decisions-ci 和 relation-api-ci JSON。
