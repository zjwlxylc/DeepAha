# Phase 2 来源观察摘要

> Release Qualification：`FAILED`
>
> Activity：`TERMINATED_WITH_INSUFFICIENT_EVIDENCE`
>
> 收口日期：2026-08-23

## 最终可计入窗口

| 指标 | 实际值 |
| --- | ---: |
| 已完成轮次 | 1 / 5 |
| 已完成 Endpoint 最终结果 | 10 / 50 最低要求 |
| 有效结果 | 10（全部 `SUCCEEDED`） |
| 无效结果 | 0 |
| 暂态有效率 | 100%（样本和时长不足，不能作为最终 Release Qualification 有效率） |
| 窗口开始 | 2026-08-22T23:36:05.8610526+08:00 |
| 第 1 轮完成 | 2026-08-22T23:36:57.1447429+08:00 |
| 实际观察跨度 | 约 51 秒，未达到至少 24 小时 |
| 原计划下一轮到期 | 2026-08-23T05:36:57.1447429+08:00（未运行） |

该仓库外 observation JSON 为 22,243 bytes，SHA-256
`6e6427e750a21abf77303221be5720061e4cbb11670f303c14cfcd24ec4e71d9`。

Registry 登记了 10 个 active 官方 Endpoint；每个最小间隔 21,600 秒、最多三次尝试、30 秒
单次超时、浏览器策略 `NEVER`，内容使用边界为 `LINK_ONLY`。这些是配置事实，不是完整 live
可用性证据。第一轮 10 个 Endpoint 均形成有效最终结果，但单轮结果不能证明五轮稳定性、至少
24 小时连续性、最终维护成本或至少 50 个结果上的 `>=98%` 有效率。

## 已作废的机器重启前窗口

另一仓库外 JSON 从 2026-08-22T01:12:27.8049656+08:00 开始，完成 4/5 轮、40 个最终结果，
其中 40 个有效、0 个失败；最后一轮于 2026-08-22T20:02:36.4178889+08:00 完成。文件为
78,559 bytes，SHA-256
`bc6ee17b310e746d2d90e843a4154e1813224e2393b26144069905e32bff51e4`。

机器死机重启后，承载该窗口的 PostgreSQL `tmpfs` 与 S3 运行证据不再可用，无法继续核对 JSON
与数据库 observation/health、RawArtifact 和对象存储之间的审计关系。因此该窗口已作废；其
40 个结果只作为事故审计记录，不能计入 Release Qualification，也不能与重启后的 10 个结果
拼成 50 个结果。两个 JSON 均保持仓库外，不提交官方网页响应、对象内容、cookie、凭据或数据库。

## 终止与清理

2026-08-23 用户明确要求直接收口并停止自动化。自动化
`deepaha-phase-2-live-gate-heartbeat` 已删除；Docker Desktop 恢复后确认
`deepaha-phase2-live-gate-postgres-1` 和 `deepaha-phase2-live-gate-s3-1` 均为
`Exited (255)`，随后按精确 compose project 执行 `down --volumes --remove-orphans`，删除两个
专用容器及专用网络。未删除仓库外 observation JSON，也未触碰其他 compose project。

当前没有 writer、下一轮或自动化任务。新鲜副本、live 后统一验证和最终候选远程 CI 均未运行。
因此本次 Release Qualification 以 `TERMINATED_WITH_INSUFFICIENT_EVIDENCE` 记为 `FAILED`；
Engineering Gate 保持 `CLOSED`，v0.2 保持 `IMPLEMENTED`、不得标记 `STABLE`。未来若重新申请，
必须取得新的明确授权，并从新的空环境、独立证据文件和完整门槛开始。
