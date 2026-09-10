# 跨层裁决持久化预检恢复点

当前候选 PR #40 / `aef1705fd80d6f361b8fc8e8087e11b32e1d4b2b`，工作区 `D:\DeepAha\.worktrees\integration-wma-evidence`。最后检查 CI #135 / run 34490300902：6 项成功，integration、phase3-resolution、web-quality 仍运行，未出现失败，尚未合并。恢复时重新确认全部 9 项结果；不能使用本记录代替当前 CI。

本轮只读取现有持久化模式及隔离 PostgreSQL；没有新增迁移、数据库写入或修改已提交契约。原 GROUP applicability 的 SQL guard 会重算 p9b_canonical_json 摘要，不能不加区分地套到新完整跨层快照。

实际 SELECT 预检：当前 `web/tests/cross-level-fixture.json` 的完整 Python/SQL 摘要一致；`1.0` 一致；合成 `1e-7` 在 Python 为 `1e-07`，JSONB 为 `0.0000001`，摘要不同。证据 `evidence/2026-09-10-cross-level-persistence-preflight.json`。这是新存储设计的表示边界，不是当前 WMA 数据错误，也没有否定已通过的当前样本。

复现：Python 对 `{"weight": 1e-7}` 使用 `json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)`；用参数绑定将其传入 `SELECT p9b_canonical_json(CAST(:payload AS jsonb))`，比较 UTF-8 SHA256。测试连接仅限已有隔离测试数据库。

安全暂停点在数据库迁移和服务实现之前。下一步用高档确定完整冻结内容的存储与摘要边界，再落实：可以考虑保留规范化 Python JSON 原始字节/文本及摘要，以单独 JSONB 投影服务引用约束；必须检查文本与投影的绑定、整数/浮点/指数/负零、Unicode，以及读取回放的一致性。此方案尚未实施或定为契约。

禁止为了新提案存储改写旧摘要、原始 artifact、Candidate Facts 或全局 p9b_canonical_json。仍需实现不可变提案、追加决策、认证 principal、事务内重载官方 block、任务/岗位/来源绑定、幂等、旧前驱/撤权/来源变化拒绝；新契约不得变成资格执行计划。确定存储方案后再推进既定数据库 → 私有 API → 桌面审核顺序。
