# 组规则适用决定的私有 API 与审核界面

本批 IMPLEMENTED，本地定向检查通过。PR #35 精确候选 `9c2cbdc` 的 CI #125 全部 9 个 job 成功，已合并为 `81fd070`；候选与合并树均为 `365d484447ad6bfcd7f0cb2097717f3ec6a60652`，证据为 `evidence/2026-09-10-group-applicability-review-ui-ci.json`。前置 PR #34 已通过 CI #123 全部 9 个 job 并合并为 `8a827e8`，候选与合并树相同。本批在 `codex/group-applicability-review-ui` 接入已有决定服务，没有修改迁移 0049、资格判断或继承计划。

新增私有 GET `unit-plans/{plan}/group-applicability-decisions/{source}/{candidate}` 与 POST `group-applicability-decisions`。请求沿用已固定版本；响应严格核对上下文、请求和证据摘要、目标身份、原文引用与快照对应、前序顺序、最新记录，以及实际审核历史精确前缀。继续复用审核授权、幂等键和 `private, no-store`。

已有组规则与岗位依据页增加明确适用、不适用、待裁决三种决定，默认不选择。桌面左侧官方段落与可编辑连续引文，右侧完整组字段和成员、当前选中的规则、决定表单及历史；窄屏堆叠。适用或不适用要求精确引用，待裁决可仅填理由。原件入口与未处理字段保留。

保存立即隐藏旧表单；使用同一 nonce 和原请求重试丢失回执，避免重复写入。成功后读取最新上下文和历史，确认回执已出现才恢复表单；更正追加新记录。页面使用固定的岗位/组规则地址，不需要保存后跳转新地址，浏览器先确认地址再刷新。分页核对上下文及最新决定，变化时隐藏旧内容；权限、过期或不可达时也隐藏完整旧内容。尚未读取到决定历史时不展示可写表单。

独立审阅发现同组多规则时表单未明确当前具体规则，新增失败测试后修复：按 `candidate.source_index` 展示本次原字段，并提供规则字段、运算符和值核对，明确只裁决这一条。复核无剩余 P1/P2。截图检查修正表单标签排布，并让原文从顶部排列。

验证：16 项 API 边界测试、1 项实际 PostgreSQL API 往返（含同键重试、前序冲突、更正、严格响应及伪造历史摘要拒绝）、31 项定向 Vitest 通过；相关 Python Ruff/格式/mypy、TypeScript、ESLint、生产构建通过。浏览器 10 项组规则测试与 2 项原岗位快照回归通过，覆盖桌面和窄屏；最后布局调整再跑两端保存/刷新/过期断言。正常保存 POST 2 / 写入 2，丢回执 POST 3 / 写入 2。未重复整站单元测试。

实际 PostgreSQL 生成的合成数据保存在 `web/tests/group-decisions-fixture.json`，浏览器服务只模拟相同的回执机制，不是 WMA 实际输出或真实人工批准。证据为 `evidence/2026-09-10-group-decisions-api.xml`、`evidence/2026-09-10-group-applicability-review-ui-validation.json` 及 `evidence/2026-09-10-group-applicability-review-ui/{desktop,mobile}.png`。

## 安全恢复点

本批 CI、合并及代码树核对已完成。下一项是将明确适用、例外与冲突组织成可回放的继承计划；它涉及公告、组、岗位多个层级和资格不变量。已在 `codex/group-inheritance-preview` 开始最小只读组条件投影，先核验完整条件、源身份与实际决定，再考虑持久化和执行。不要把已有 APPLIES 记录直接当作岗位资格或全组继承。沿用当前任务窗口和工作区。

真实样本仍为 94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED，整体资格 UNCERTAIN。本轮无 WMA、模型调用或官方下载，未改 V3 Prompt、冻结 Candidate Facts、原件和 Evidence Gate。旧岗位快照的非 UTC 会话兼容问题继续保留在前批记录中；当前验证使用 UTC。
