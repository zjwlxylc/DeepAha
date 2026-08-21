# Phase 2 来源观察摘要

> 状态：`LIVE WINDOW IN PROGRESS`

## 当前实际计数

| 指标 | 当前值 |
| --- | ---: |
| 已完成轮次 | 1 / 5 |
| 已完成 Endpoint 最终结果 | 10 |
| 有效结果 | 10（全部 `SUCCEEDED`） |
| 无效结果 | 0 |
| 当前有效率 | 100%（窗口未完成，不能作为 Gate 最终值） |
| 窗口开始 | 2026-08-22T01:12:27.8049656+08:00 |
| 第 1 轮完成 | 2026-08-22T01:13:02.3311266+08:00 |
| 下一轮到期 | 2026-08-22T07:13:02.3311266+08:00 |
| 人工维护分钟数 | 0（截至第 1 轮，无用户/人工介入） |

Registry 已登记 10 个 active 官方 Endpoint；每个最小间隔 21,600 秒、最多三次尝试、
30 秒单次超时、浏览器策略 `NEVER`，内容使用边界为 `LINK_ONLY`。这些是配置事实，不是
live 可用性证据。

live runner 已由无网络 mock 测试证明会拒绝低于策略的间隔、逐 Endpoint checkpoint 外部
JSON、隐藏响应正文与秘密，并可用同一路径续跑。数据库事务与 JSON checkpoint 不是跨系统
原子提交，当前由唯一 heartbeat 写入，禁止并发手动续跑。第 1 轮的十个 Endpoint 均一次
尝试成功；轮次完成时外部
observation JSON 为 22,243 bytes，SHA-256
`9086e3181cf04bd6d50924e5d8398a46ba68f3cc1800c79794df4c9514f842c7`。该文件会在后续轮次
原子更新，因此此 hash 只是当前有效窗口第 1 轮快照身份。轮后 CLI source health 实际退出 0，
对应 Endpoint 为 1 次 attempt、1 次 success、0 次 failure，且返回同一 Artifact digest/object key。

首次执行在任何 Endpoint GET 前暴露并修复了 Windows PowerShell UTF-8 Registry 读取问题；
第二次前置导入因 disposable 数据库尚未迁移而拒绝，应用 `alembic upgrade head` 后用同一外部
状态续跑成功。这两次前置失败没有伪造为 Endpoint 结果。

此前 `01:05:22+08:00` 开始的一轮虽然产生 10 个成功外部摘要，但为运行 verifier 临时停止
compose 后，PostgreSQL `tmpfs` 被清空，数据库 observation/health 证据不再存在。该窗口已明确
作废，不计入上述任何 Gate 计数；当前有效窗口从空数据库重新迁移后于 `01:12:27+08:00`
开始，窗口完成前禁止停止 live compose。计划阈值 `5 轮 / >=24 小时 / >=50 结果 /
>=98% 有效` 仍未满足。

实际完成后只能从仓库外 observation JSON 导出聚合值；不得提交中国官方网页响应、对象内容、
cookie、凭据或数据库。

等待期间完成的代码审查、安全扫描、离线测试和文档工作没有停止/重启 live 容器，也没有写入
observation JSON，因此不计为来源策略维护分钟。修复只影响后续代码候选；当前窗口仍按原
Registry SHA、轮次间隔和结果计数继续。
