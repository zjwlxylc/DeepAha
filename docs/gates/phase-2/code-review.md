# Phase 2 等待期代码审查

> 审查状态：`COMPLETE FOR WAITING-PERIOD REVIEW`
>
> 审查范围：`6c2db59db3d3031041c9b7af1700fa41c85ea661..5779b619dc0260a87a83bee9c5be2d5b0ff77984`
>
> Engineering Gate：`CLOSED`
>
> Release Qualification：`IN_PROGRESS`

本次审查覆盖 v0.2 契约与生成 Schema、`20260821_0002` 迁移/ORM、Source Registry、
CaptureObservation、同步 HTTP 采集、源健康/CLI、解析持久化、HTML/PDF/XLSX 解析器、
Evidence Locator、live runner 及其测试。审查以 Phase 2 spec、Task 1–11 实施计划和 v0.1
兼容边界为准；没有把仍在运行的 live 窗口或计划阈值当作验证事实。

## 已修复发现

| 严重度 | 发现 | 修复与回归证据 |
| --- | --- | --- |
| `Important` | Registry 导入器把旧 Endpoint 的 `active: true → false` 当作策略冲突，无法执行契约允许的单向停用。 | 只允许带更晚 `updated_at` 的单向停用；继续拒绝重新启用和策略字段就地改写。RED/GREEN：`test_old_endpoint_version_can_be_deactivated_without_rewriting_policy`。 |
| `Important` | XLSX 解析器信任 worksheet 声明维度；很小的文件可伪造 `A1:XFD1048576`，导致遍历巨大空网格。 | read-only 流式解析前重置声明维度，以实际 worksheet XML 为准；回归覆盖伪造最大维度。RED/GREEN：`test_xlsx_parser_ignores_untrusted_declared_worksheet_dimensions`。 |
| `Important` | Endpoint 与重定向 URL 可携带 `user:password@host`，存在隐式 Basic Auth 与凭据外传风险。 | Pydantic、JSON Schema、Registry 导入和每次重定向前置检查均拒绝 URL 用户信息。RED/GREEN：契约、Registry 与 collector policy 三层测试。 |

没有发现未解决的 `Critical` 或 `Important` 级问题。上述修复在提交
`5779b619dc0260a87a83bee9c5be2d5b0ff77984` 中完成；定向 contracts/sources/documents
测试 `152 passed`，隔离基础设施集成测试 `69 passed, 159 deselected`，安全的根验证
`scripts/verify.ps1` 退出 0，远程 CI run
[32518043724](https://github.com/zjwlxylc/DeepAha/actions/runs/32518043724) 成功。

## 受控剩余风险

- live runner 没有跨进程 single-writer lock。数据库事务与仓库外 JSON checkpoint 也不是
  跨系统原子提交；当前由唯一 heartbeat 写入，禁止并发手动续跑。中断发生在采集命令与
  checkpoint 之间时，必须先核对数据库与 JSON，不能盲目续跑。
- collector 在请求前解析并检查 DNS/IP，但实际 HTTP 客户端会再次解析，仍存在 DNS
  TOCTOU/rebinding 窗口。当前 Registry 是受版本控制、人工核验的固定官方 host；若未来接收
  不受信任 URL 或进入生产云，需要更强的解析固定/网络出口隔离。
- ObjectStore 读取对象时会把完整字节载入内存。live collector 已把单次响应限制在 25 MiB，
  但内部手工导入的超大对象仍需由操作边界控制；流式对象读取属于后续生产加固，不在 Phase 2。
- 本次是实施者按审查清单完成的自审，不等于独立业务/安全评审；远程 CI 只提供可复现性证据，
  不替代后续 Gate 候选的独立核验。

## 判定

本次审查没有未解决的 `Critical` 或 `Important`，与迁移、契约、测试、安全及 scope 证据共同
支持 Phase 2 Engineering Gate `CLOSED`。该判定不把 v0.2 标记为 `STABLE`；五轮 live、
新鲜副本、最终统一验证及精确候选提交远程 CI 仍属于 Release Qualification，必须实际成功。
