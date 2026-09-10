# 单位组规则预览管理页面

状态 IMPLEMENTED。PR #30 候选 `032728b` 的 CI #115 全部 9 项通过，合并为主线 `8128fbf`，候选与合并代码树相同。精确回执见 `evidence/2026-09-10-group-rule-preview-ui-ci.json`。分支 `codex/group-rule-preview-ui` 基于后端 PR #29 同树合并的主线 `78a1f9d5e5b566974d48aca75be8cbbfb24ba732`。

组字段审核记录新增只读预览入口，固定地址 `/review/investigations/{taskId}/group-facts/{prepId}/rules`。页面强制动态读取，服务器动作重新读取并检查当前组字段回执，与预览中的精确组身份、完整回执、全部字段索引、候选、事实状态、引用集合及摘要核对。没有新增后端写入；预览中未知、拒绝和未处理条件不能升级为可执行规则。

桌面以原文证据和预览结果并排展示，窄屏堆叠；保留原始状态、备注、官方原件入口、定位、未知/未处理行和其他层级排除记录。页面没有批准、保存或岗位继承入口。读取中和失败后隐藏旧内容，恢复只由用户明确重新读取触发。首页及公开用户端未改。

验证：33 个定向测试通过（动作 17、组件/新路由 7、原组字段组件/路由 9）；12 个相关文件 ESLint 和 TypeScript 检查通过。新增路由生产构建通过，未重跑整站单元测试。Playwright 桌面 1280×900、窄屏 390×844 共 20 项通过（新预览 8、原组字段 12）：固定地址跳转后刷新、未知/未处理显示、过期/权限/不可达隐藏及显式恢复。新预览浏览与恢复均保持后端 POST 0、变更 0。两张截图已检查，无横向溢出或遮挡，保存在 `evidence/2026-09-10-group-rule-preview-ui/`。

独立只读评审未发现 P1/P2，详见 `evidence/2026-09-10-group-rule-preview-ui-validation.json`。浏览器 API 与审核账号均为合成测试，不是真实人工批准。本批未运行 WMA、未下载官方文件、未改冻结 Schema、CandidateFacts、原始 quote 或 locator。实际样本仍为 94 PASS / 0 FAIL / 30 Word UNVERIFIED；Delivery UNVERIFIED，整体资格 UNCERTAIN。

本批 CI 与同树合并已完成。后续组规则持久化与独立审核见 `2026-09-10-group-rule-review.md`。岗位适用范围与例外继承继续后置，不随规则批准自动放行。无需新任务窗口。
