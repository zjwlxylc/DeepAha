# SG8-A｜以后每次升级怎么做

## 正常升级

```text
本地修改
→ 自动测试
→ staging 部署
→ 人工验收
→ production 自动备份
→ release symlink 切换
→ Smoke
```

以后不要 SSH 上去直接编辑 production 源码。

## Code rollback

```bash
sudo bash ops/sg8a/rollback.sh production
```

它只在 `RELEASE_COMPATIBILITY.json` 的 `database_generation` 相同情况下自动执行。

如果数据库代际不同，脚本**拒绝自动回退**。这时必须结合该版本数据库迁移说明决定是否恢复备份，不能只切代码。

## Backup

```bash
sudo bash ops/sg8a/backup-postgres.sh production
sudo bash ops/sg8a/verify-backup.sh /var/backups/deepaha/production/TIMESTAMP
```

备份会短暂停止 API/Worker，保证 PostgreSQL snapshot 与本地 write-once 原件目录处于同一静止窗口。Public Beta 早期宁可接受短暂停机，也不要做看似“在线”但无法证明一致性的备份。

## Restore

恢复工具只允许**空 PostgreSQL + 空原件目录**：

```bash
sudo bash ops/sg8a/restore-postgres-backup.sh /etc/deepaha/drill.env BACKUP_DIR
```

它不会 `DROP` 现有生产库。真实灾难恢复应先新建空库恢复、验证，再切连接；不要在原生产库上直接覆盖。
