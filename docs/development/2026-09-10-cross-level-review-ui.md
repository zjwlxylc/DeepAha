# 跨层级条件私有接口与审核页面

本批 IMPLEMENTED，本地定向验证通过，独立复核无剩余可复现 P1/P2；精确候选 CI 待提交后检查。不是人工关系裁决或可执行资格计划。

私有 GET `/{task}/unit-plans/{plan}/cross-level-preview` 调用真实只读重建服务，使用既定 CrossLevelReview 响应契约，校验请求 task/plan 与返回身份，返回 private, no-store。完整原始输入、来源版本、审批关联和摘要校验仍在后端，不接受客户端提交的继承结果。

岗位快照页增加 `/review/investigations/{task}/unit-plans/{plan}/cross-level` 入口。桌面双栏、窄屏堆叠，展示公告、组和岗位完整分母，包含不适用及待处理项；每行保留原始条件、引用、原件下载及定位、范围理由和来源审核入口。同字段审核索引可跳到准确卡片，只表示需要复核，不自动判断累积、例外或冲突。基础快照状态与后续范围决定分别标注；资格仍为 UNCERTAIN。

重读立即隐藏旧条件和审核索引；403/409/503 后没有残留旧内容，恢复后可重新读取。同地址服务端刷新按完整响应重新挂载，避免保留旧状态。没有保存、批准或执行控件。

复核定位并修复了三项接入表示差异：Unicode 排序按 Python 码点统一，避免 emoji/全角字符顺序误报；锚点 DOM id 保留原文本、URL fragment 编码，避免 source:0 等 ID 跳转失败；完整原始输入摘要留在后端验证，避免 response.json() 把 1.0 解析成 1 后错误重算。前端继续重建完整派生结果，并检查身份、版本、全部行、指针、适用状态、审核组、blockers 和仅含契约整数/字符串/布尔的派生摘要。没有更改旧摘要或降低 Evidence Gate。

## 验证与证据

- 6 项 API 权限/状态/身份测试，2 项实际 PostgreSQL → 服务 → API 往返通过。
- 34 项前端定向及关联测试通过，其中 22 项为本批 action/UI/Unicode 测试，12 项为相关已有组件回归；没有重跑整站单元测试。
- 桌面和窄屏各验证正常地址刷新、最后条件索引跳转、失效、撤权、故障及恢复，共 6 项通过。截图检查无横向溢出。
- Ruff、格式、mypy、TypeScript、定向 ESLint 和本批生产构建通过；构建只因实际前端变更及后续修复运行。
- `evidence/2026-09-10-cross-level-api.xml`、`evidence/2026-09-10-cross-level-api-boundary.xml`、`evidence/2026-09-10-cross-level-review-ui/{desktop,mobile}.png`。
- `web/tests/cross-level-fixture.json` 来自隔离 PostgreSQL 的实际合成导出。未处理组条件保留 locator.weight=1.0，原定位仍不可机械核验，没有升为 PASS；前端从原始 JSON 文本解析后可正常展示，原摘要保持不变。

## 恢复顺序

工作区 `D:\DeepAha\.worktrees\integration-wma-evidence`，分支 `codex/cross-level-review-ui`。先检查本批精确候选 CI，全部成功后合并并核对树。下一项是人工跨层级关系裁决契约：需要设计例外、累积和冲突的明确语义、精确证据与条件绑定、独立审核、修订及失效回放，然后再实现持久化与后续编译。这一步适合高档，当前停在接口与页面交付完成的安全点，不要在中档收尾时顺手新增裁决语义。

真实样本沿用前轮证据，本批没有实时重验：124 = 94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED，资格 UNCERTAIN。无 WMA、LLM、官方下载、V3 Prompt、Candidate Facts、原始引用或 Evidence Gate 改动。合成账户和浏览器样本不是独立真人验收或发布资格证据。
