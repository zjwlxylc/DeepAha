# 跨层条件关系裁决契约交付

本批 IMPLEMENTED：实现 `cross-level-adjudication/1.0.0` 的不可变关系提案、独立审核记录、连续历史及确定性回放。范围为纯契约，不新增数据库写入、接口或审核控件；发布资格未因此改变。

提案绑定完整 CrossLevelReview 和精确所选条件。支持同时满足、定向例外、冲突和未决；例外不会删除原条件。明确关系要求每个条件的证据及整组关系的证据。原文引用与定位不改写，结构通过不代表已核验官方内容或已获真人批准。

审核者不得与提案生产者相同；历史必须连续、时间有序，未知关系不能被批准。离线使用另行保存的整个包摘要防止截断与重算伪造。当前来源另行提供，同任务/岗位的上游完整快照变化会标 STALE，其他任务/岗位直接拒绝。完整分母、原 blockers、executable=false 和资格 UNCERTAIN 始终保留。

验证中修复：基础计划是 Pydantic OriginalPlan，目标读取使用其属性；被 REJECT 的 CONFLICT 提案不再加“冲突已记录”标记，只有当前获批冲突才加该标记。

## 验证

- 47 项本批契约测试、22 项现有跨层及 GROUP 契约回归，共 69 项通过。证据 `evidence/2026-09-10-cross-level-adjudication-contract.xml`。
- Ruff 格式、检查及定向 mypy 通过。没有修改前端或数据库，不重跑构建、浏览器或数据库测试。
- 使用已合并的真实 PostgreSQL/API 合成导出。新关系和审核记录为合成结构测试，不证明独立真人完成了语义裁决；新增上游历史是合成追加，不是新的数据库执行结果。
- 独立代码复核无剩余可复现 P1/P2，复核者独立重跑同三组 69 项测试全部通过。PR #40 候选 `aef1705` 的 CI #135 全部 9 项成功，合并为 `d75bb9f`；候选与合并树同为 `6cfae0a0bc5d1d5381c56877a6e20a5016eafa25`，证据 `evidence/2026-09-10-cross-level-adjudication-ci.json`。

## 下一步与恢复

工作区 `D:\DeepAha\.worktrees\integration-wma-evidence`，分支 `codex/cross-level-adjudication-contract`。先确认本批精确候选 CI，成功后合并并核对树。

高不确定性的语义边界已落实为契约与反例。下一批可用中档按已有服务模式接入不可变提案持久化和追加审核历史：受信服务重建全快照与官方 block，认证账号身份，不接收客户端自报的来源或审核人；事务中验证旧前驱、幂等、撤权与来源变化，实际 PG 验证后再接私有 API 和桌面页面。详细边界见 `docs/superpowers/specs/2026-09-10-cross-level-adjudication-contract.md`。出现重叠提案冲突、条件性例外或资格编译新语义时，再评估是否切回高档。

真实样本状态沿用此前证据，本批没有重新调查：124 = 94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED。没有 WMA、Prompt、Candidate Facts、原始证据或 Evidence Gate 变更。
