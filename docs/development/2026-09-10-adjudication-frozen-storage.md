# 裁决包冻结存储交付与恢复

本批实现冻结文本封装和读取校验，解决新持久化接入时 Python 与 JSONB 对数字表示不同的问题。完整包沿用现有 digest，不从 model_dump 或数据库数值投影重新生成内容；旧时间戳拼写、原文、定位和上游快照保持不变。

冻结文本是唯一摘要依据，UTF-8 SHA256 直接对文本计算。JSONB 采用数据库生成列，仅供查询和关联，禁止独立写入。解封必须另传可信完整包摘要，同时重新验证 AdjudicationPackage。封装自洽不构成人工认证、证据真实性或来源当前性证明。

20 项新存储测试与 47 项已有裁决契约测试，共 67 项通过；真实 PostgreSQL 六种数字往返及特殊字符拒绝共 7 项通过。Ruff 格式/检查、mypy 通过。证据：`evidence/2026-09-10-adjudication-storage-unit.xml`、`evidence/2026-09-10-adjudication-storage-postgres.xml`、`evidence/2026-09-10-adjudication-storage-postgres-edge.xml`。数据库使用事务临时表，验证文本、生成投影及摘要约束，不是正式业务持久化完成证明。

## 恢复顺序

工作区 `D:\DeepAha\.worktrees\integration-wma-evidence`，分支 `codex/adjudication-frozen-storage`。PR #40 已通过并合并；本批独立复核无可复现 P1/P2，复核者独立重跑 20 项新测试通过，提交后的 CI 尚需确认。下一批先确认本批精确候选 CI、合并及树一致，再按 `docs/superpowers/specs/2026-09-10-adjudication-frozen-storage.md` 接正式提案表和追加审核表。

已确定的数字与历史摘要边界无需重做：正式表须存储版本、文本摘要约束和生成 JSONB 投影，同时补上业务不可变触发器、task/plan/账号关联、幂等和前驱规则；服务必须从认证 principal、当前全快照和官方 block 重建提案与审核输入，事务内重查权限和当前性。未来读回必须使用文本；JSONB 同值比较不保护数值表示，也不能作为旧摘要输入。数据库拒绝不可表示字符时整笔回滚，不能改原文。

后续属于已确定契约下的持久化接入，可切到中档推进；若需要改变资格语义或跨提案冲突裁决，再评估高档。当前没有正式业务迁移、HTTP 入口或审核保存控件；没有 WMA 重跑、旧摘要/Prompt/事实/Evidence Gate 更改，真实 Delivery 未因此通过。
