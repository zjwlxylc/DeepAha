# 跨层级条件只读组合与回放

本批内部服务与契约 IMPLEMENTED，本地定向验证通过，独立定向复核无剩余可复现 P1/P2。PR #38 精确候选 `f02cca4` 的 CI #131 全部 9 个任务成功，已合并为 `9638af9`，候选与合并树均为 `11be05351e8eb6e9e226adf1c149fd97c05679f6`，证据 `evidence/2026-09-10-cross-level-ci.json`。接口与页面后续交付见 `2026-09-10-cross-level-review-ui.md`；持久化裁决和跨层级资格执行尚未完成。

新增 `cross-level-condition-review/1.0.0`，组合实际数据库中同一完整 v2 基础计划上的公告、GROUP 和 UNIT 条件。每个 manifest 条件恰有一行，保留来源定位指针和完整上游快照。LOCAL 仅表示岗位层来源；INHERITED / EXCLUDED / UNRESOLVED 只表示范围处理状态。

跨层级同名字段生成待审索引，明确排除项也保留；不自动认定冲突、例外或覆盖，更不因岗位要求更具体而覆盖公告要求。索引不是完整语义冲突检测器。固定 executable=false、overall_qualification=UNCERTAIN，保留上游未决标记。v2 计划逐字段不变。

在线预览在同一事务内从真实记录重建两次，重新授权，拒绝输入改变。只读服务不接受客户端提交的继承结果。离线回放必须另传在线导出时独立保存的可信依赖摘要，先检查实际完整依赖内容，再校验确定性投影；不得用待验包自己的摘要作可信锚。摘要锚不认证人类身份或当前性。旧公告投影函数不承担离线审批验证；未知活动 compiler / adapter 和不匹配的公告源行摘要、分母另行拒绝。

独立复核发现公告投影函数不验证内部审批关联，曾允许修改源行后重算包内摘要仍回放。现通过上述独立摘要锚和冻结源行校验修复，并补充实际 PG 输出中的原始值、目标岗位、回执摘要、批准记录、未知 compiler 篡改反例。撤权测试曾同步等待服务持有的共享账号锁，已修正为事务内故障注入以检查再次授权；来源禁用仍用独立事务注入。此为测试方式修正，没有调整业务锁或撤权逻辑。

复核还定位到旧 GROUP 契约的 derivation_version 是普通字符串，新组合边界已显式限定支持版本，并用重算所有相关摘要后的未知版本构造证明修复前失败、修复后拒绝。

验证：22 项离线／既有 GROUP 契约测试通过；4 项实际 PostgreSQL 测试通过（含三层更正、五种包内篡改、未知版本、源行冻结摘要、完整分母、无写入、v2 不变、再次授权、来源失效和读间变化）。Ruff、格式、mypy 通过。没有前端变更，复用已通过的前端构建与浏览器证据，未重跑整站测试或生产构建。

证据：`evidence/2026-09-10-cross-level-replay.xml`、`evidence/2026-09-10-cross-level-integration.xml`。最后增加 GROUP 派生器版本检查后，实际三层 PostgreSQL 正例再次通过，证据 `evidence/2026-09-10-cross-level-final-positive.xml`。所有新输入和审核账号均为合成测试，不是实际独立真人验收。

## 恢复顺序

本批 CI 与合并树核对已完成。沿用工作区 `D:\DeepAha\.worktrees\integration-wma-evidence`，接口与页面批次在分支 `codex/cross-level-review-ui`。再后才设计人工关系裁决、持久化和新的执行契约，不能把组合预览直接交给 v2 编译器。

真实样本基线沿用前轮证据，本批没有实时重验：124 = 94 PASS / 0 FAIL / 30 Word UNVERIFIED；Delivery UNVERIFIED，资格 UNCERTAIN。无 WMA、LLM、官方下载、V3 Prompt、Candidate Facts、原始引用或 Evidence Gate 改动。
