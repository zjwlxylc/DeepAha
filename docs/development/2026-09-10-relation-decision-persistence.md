# 关系提案的独立审核历史

本批在冻结提案上追加 `investigation_relation_decisions`，提供 `save_relation_decision`，并让 `load_relation_proposal` 返回完整历史及当前回放。审核身份由认证 principal 获取，禁止提案生产者自审；序号、时间与 ID 由服务端生成。仅实现持久化服务，不增加 API/UI，不激活资格规则。

每条决定保存原始规范 JSON 文本、字节摘要、生成的 JSONB 查询投影、原始请求及前驱。数据库禁止覆盖与删除；同提案的任务锁、唯一序号和前驱校验防止并发分叉。已有历史时降级迁移明确拒绝。服务读回重新校验字节、请求关联及完整契约链，完整提案 hash 由 Python 契约核对，避免 PostgreSQL 对任意数值的表示差异。

审核可以追加 APPROVE / REJECT / NEEDS_ADJUDICATION，UNRESOLVED 不能批准。原提案不改写。创建提案接口保留原始创建收据；当前读取返回全历史包。决定请求的 `expected_proposal_payload_hash` 使用响应中稳定的 `proposal_payload_sha256`，始终指向原始空历史提案摘要；读取响应的 `payload_sha256` 是当前完整包摘要，两者用途不同。旧幂等请求返回其原决定收据及最新回放，不能让历史批准重新成为当前批准。

来源变化使当前回放为 STALE，禁止追加新决定；历史读取和原请求收据仍可用于审计。写入前后再次检查账号资格和来源。所有状态始终 `executable=false`，不改变硬资格 UNCERTAIN；工程测试里的合成审核账号不构成真人独立签署。

## 前序集成

PR #42 的精确候选 `1b8cfd83161117716919eb3b2fea52f932b22507` 已经 CI #139 九项通过，合并为 `6151547eaf4fba1421b2c59fd547b8f82f12d8df`；两者 tree 均为 `ac9bb4deee8dda841198a925bf04ce4b83ec0bb5`。证据见 `evidence/2026-09-10-relation-proposals-ci.json`。

## 本地验证

- `evidence/2026-09-10-relation-decisions.xml`：9 项 PostgreSQL 集成测试通过（139.14 秒），含前驱、自审、摘要、幂等、不可覆盖/删除/降级、来源失效、并发分叉及写入后撤权回滚。
- `evidence/2026-09-10-relation-decision-compatibility.xml`：UNRESOLVED 禁止批准与原提案读取兼容共 2 项通过（32.16 秒）。
- 独立代码评审发现刷新后摘要用途混淆，已增加稳定 `proposal_payload_sha256`。失败回归确认缺字段后修复，`evidence/2026-09-10-relation-decision-refresh.xml` 中刷新后继续审核及原提案兼容 2 项通过（45.72 秒）。其余未发现明确 P1/P2；评审者运行了两组纯单元模块，未运行数据库。
- Ruff 格式与检查、定向 mypy 均通过。隔离测试数据库空表从 0051 降到 0050，再升级 head，`alembic check` 无差异。未重跑整站测试或生产构建。

## 集成与恢复

本批相关测试、迁移和评审完成后提交候选，待精确候选 CI 通过再合并。下一批统一接私有审核 API，再接桌面审核页面。保持原 Evidence Gate、Prompt、Candidate Facts 和原件不变，不调用 WMA。
