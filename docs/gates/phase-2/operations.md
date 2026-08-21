# Phase 2 运行说明

## 离线统一验证

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-phase2.ps1
```

脚本先运行根验证，再启动 PID-scoped PostgreSQL/S3，锁定依赖、升级迁移、运行全部 integration
及 contracts/sources/documents 离线测试、检查 Alembic 漂移，并在 `finally` 中只清理自身 compose
project。脚本不设置 live 权限、不删除 volume、不使用浏览器。

## live 观察

先为本次窗口启动 disposable PostgreSQL 18 与 S3，并对该空数据库执行：

```powershell
Set-Location backend
uv run alembic upgrade head
Set-Location ..
```

```powershell
$env:DEEPAHA_ALLOW_LIVE_SOURCE_CHECK = "true"
powershell -ExecutionPolicy Bypass -File scripts/run-phase2-source-observation.ps1 `
  -Rounds 5 -IntervalSeconds 21600 `
  -OutputPath "<repository-external-path>\phase2-source-observation.json" `
  -RunDueRoundsOnly
```

使用同一 output path 续跑；只在 `next_due_at` 到达后运行下一轮。每次调用最多完成一个到期轮次，
避免长时间阻塞；不能缩短 21,600 秒间隔。数据库/S3 必须是仓库外 disposable 实例，观察 JSON
不得提交。实际排障和策略维护时间按人工分钟记录，不从日志推算。

当前 `infra/compose.yaml` 把 PostgreSQL 数据目录放在 `tmpfs`。有效 live 窗口期间不得
`stop`、`down` 或删除 `deepaha-phase2-live-gate`，也不得运行会抢占 55432/55000 端口的
Phase 1/2 集成 verifier；应在第五轮安全导出聚合证据后再清理。一次因停止容器丢失数据库
证据的早期轮次已经作废并从零重启，未计入 Gate。

当前 heartbeat `DeepAha Phase 2 live Gate heartbeat` 每 6 小时唤醒本任务，检查
`next_due_at` 后才续跑；失败时通知，Gate 解决后停用。heartbeat 不改变 Registry、间隔、
阈值或访问边界。

## 恢复与停止

- 外部 JSON 使用临时文件替换，并在每个 Endpoint 后 checkpoint；重跑跳过 JSON 中已经
  checkpoint 的 Endpoint 结果。
- collector 的数据库事务与外部 JSON 不构成跨系统原子提交。runner 目前没有跨进程锁，
  同一 observation path/数据库必须只有一个 writer；heartbeat 活跃时不得并发手动续跑。
- 若进程在 collector 已提交、JSON 尚未 checkpoint 的窗口中中断，先比较数据库 observation、
  health 与外部 JSON，再决定恢复方式；不得盲目重跑并把额外观察删除或伪装成原结果。
- 配置、轮数、间隔或 Registry SHA 不一致时拒绝复用旧 observation 文件。
- 任一策略违规、需要特例绕过或有效率不达标时保留证据并保持 Gate OPEN。
