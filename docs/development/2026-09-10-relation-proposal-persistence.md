# 不可变关系提案持久化

实现正式 `investigation_relation_proposals` 表与 `save_relation_proposal`、`load_relation_proposal`。本批只保存提案，没有审核批准写入或 API/UI 控件，资格保持 UNCERTAIN。提案生产者来自认证人工 principal，不接受客户端自报 producer 或 source_review。

服务从当前数据库重建完整 CrossLevelReview，核对请求摘要；根据当前 task/source bundle 的 member、block 和逐字 quote 绑定证据，保存不可变冻结文本及摘要。JSONB 由数据库生成，读回从文本解封并验证原提案、请求、目标、证据及时间。同岗位/账号/幂等键复用同一记录，键冲突拒绝。保存前、写入后和读取结束前再次授权及重建来源。

数据库约束保护 task→plan 归属、producer 资格、基本请求关联、字节摘要、存储版本、幂等唯一性，触发器禁止 UPDATE/DELETE；业务深层投影和证据重建由服务承担。数据库原始写入权限不能暴露给客户端。空表支持降级/升级；存在提案时拒绝降级删除历史。

旧范围决定改变后，读取原包不改写，回放为 STALE；旧请求不能借幂等重试重新当作当前提案。提案被保存只表示人工解释候选留档，不代表独立审核完成或官方语义已验证。

## 验证与恢复

最终 11 项实际 PostgreSQL 测试全部通过（118.24 秒），覆盖保存/读取不改变基础计划、重试、错误 quote/member/hash/target/幂等、数据库修改删除及有历史时降级拒绝、来源变化、两阶段撤权回滚、并发同键唯一；证据 `evidence/2026-09-10-relation-proposals-final.xml`。空表迁移降级/升级后 alembic check 无差异；曾出现长约束名被 PostgreSQL 截断的差异，改为短名后通过。Ruff 格式/检查与 mypy 通过；独立代码复核无可复现 P1/P2（复核者未运行数据库）。本批候选 CI 待提交后确认，不以本地测试代替远程结果。

工作区 `D:\DeepAha\.worktrees\integration-wma-evidence`，分支 `codex/relation-proposal-persistence`。接下来先确认本批精确候选 CI 和合并，再接独立审核者的追加决策记录（顺序、前驱、幂等、自审拒绝与失效），随后统一接私有 API 与桌面页面。无需改变已确定的关系语义或冻结存储契约。

没有修改 Prompt、Candidate Facts、原始证据、旧摘要或 Evidence Gate，也没有重新调用 WMA。真实 Delivery 的 Word 待核验状态未改变。本批合成账号与条件用于工程验证，不代替真实人工审核或发布资格。
