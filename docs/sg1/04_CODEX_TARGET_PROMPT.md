# Codex Target Prompt｜SG1 可行动机会粒度

你在最新 DeepAha 工作树执行 **SG1**。这是当前最高优先级目标。

## Goal
把用户机会总览的基本单位从“公告/网站级 Publication”改成“用户能够独立收藏、提醒、资格判断和行动的具体岗位/赛道/项目分项”，同时保留父公告作为审核、版本和证据上下文。

最终必须看到：**1份公告含N个真实岗位 → 总览出现N个具体岗位，而不是1张打包公告卡。**

## Read first
`AGENTS.md`、本规划 `01_CURRENT_STATE_AUDIT.md`、`02_ACTIONABLE_OPPORTUNITY_GRANULARITY_SPEC.md`、`03_SG1_IMPLEMENTATION_PLAN.md`、`06_ACCEPTANCE_GATES.md`、`08_CODEX_TARGET_MODE_PROTOCOL.md`。

## Must preserve
- Direct WMA；
- immutable raw artifacts；
- Source/Brief；
- overall APPROVE/REJECT；
- root Opportunity identity；
- local notes/usage restrictions；
- old readable content and rollback path。

## Must not restore
旧 Provider、方法认证、逐字段人工审核、规则审批前置、Native Automation Worker、大模型逐用户全量匹配。

## Acceptance is the contract
至少证明：
1. 1 root + 2 POSITION → catalog=2；
2. GROUP 不出卡；
3. root-only → singleton=1；
4. unit id 跨版本稳定；
5. search/filter/card/detail 都是 unit-first；
6. save/reminder/feedback/fit 对 A01/A02 相互隔离；
7. review 仍只需一次整体决定；
8. old data 可升级；
9. 100+ unit 有界分页；
10. 至少一份真实多岗位 WMA 返回完成端到端本地验证。

你可以根据仓库现状调整具体文件结构，但不能用“前端平铺 children”绕过 target identity 和用户状态粒度。

执行 RED→GREEN，生成 migration/backup 证据和 `SG1_ACTIONABLE_GRANULARITY_DELIVERY.md`。每个局部失败最多3次自修复；仍不成立则停止并报告。

不要继续 SG2，不 merge/push/deploy。
