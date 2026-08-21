# Phase 2 验收结果

> Gate 状态：`OPEN`
>
> 实现状态：`IMPLEMENTED`

## 退出条件逐项状态

| # | 退出条件 | 当前状态 | 已有证据或缺口 |
| --- | --- | --- | --- |
| 1 | 相同真实语义抓取产生两条观察、一个 RawArtifact | `LOCAL PASS` | 脚本化采集集成测试证明同字节两次成功保留两条 CaptureObservation 并复用一个 RawArtifact；live 重复内容证据待观察窗口产生。 |
| 2 | 失败和 304 独立记录，且 Artifact 关系正确 | `LOCAL PASS` | 集成测试覆盖失败不建 Artifact、304 引用既有 Artifact、每次尝试独立 observation 和稳定错误码。 |
| 3 | 十个官方 Endpoint 完成 live 窗口及健康/维护证据 | `PENDING` | 尚无五轮、24 小时、至少 50 个最终结果；不得写成通过。 |
| 4 | HTML/PDF/XLSX 产生确定性 Document、派生文本和 locator | `LOCAL PASS` | 固定 fixture 与官方 GOV.UK HTML 的字节身份、解析结果和 locator replay 测试通过。 |
| 5 | 原始对象不被覆盖，解析升级保留旧 Document | `LOCAL PASS` | DocumentService 集成测试比较解析前后 Artifact 身份，并证明新 parser version 创建新 Document、旧结果保留。 |
| 6 | v0.1/v0.2 Schema、迁移、ORM、契约一致 | `LOCAL PASS` | 迁移 `20260821_0001 → 20260821_0002`、68 个集成测试、确定性 Schema 测试及 `alembic check` 通过；v0.2 在 Gate 关闭前仍保持 `PROPOSED`。 |
| 7 | 新鲜环境可复现且默认测试离线 | `PARTIAL` | 当前工作树默认 155 个测试通过且 marker 排除 integration/live；精确候选提交的新鲜副本尚未运行。 |
| 8 | 未进入 Phase 3，且无禁止基础设施/数据/产物 | `PARTIAL` | 当前实现未创建 Opportunity Resolver/Version/Event、LLM、队列、用户/API/UI；最终 scope/secret/artifact 扫描与远程候选提交仍待完成。 |

## Gate 判定

本地实现证据不足以替代 live、新鲜副本和远程 CI。Phase 2 Gate 当前判定为 `OPEN`，
领域契约 v0.2 不得标记 `STABLE`，不得进入 Phase 3。
