# DeepAha 3.8.0-rc1 / SG8-A 部署入口

SG8-A 是当前正式部署入口。旧 `docs/rebuild/06_DEPLOYMENT.md` 仍保留为重建阶段历史资料，但**不再作为公网发布默认流程**。

请按顺序阅读：

1. `docs/sg8_a/00_START_HERE.md`
2. `docs/sg8_a/02_DATA_MIGRATION.md`
3. `docs/sg8_a/03_SERVER_DEPLOYMENT.md`
4. `docs/sg8_a/04_RELEASE_ROLLBACK.md`
5. `docs/sg8_a/05_VALIDATION.md`

核心规则：

- 本地继续使用 `C:\Users\LENOVO\deepaha-data` / SQLite 开发与验收；
- 公网 staging/production 使用**独立 PostgreSQL**；
- 先 `staging.deepaha.com`，后 `www.deepaha.com`；
- 服务器源代码按 `/opt/deepaha/releases/<version>` 版本化，不直接在线编辑；
- `/var/lib/deepaha/*` 数据目录与 release 分离；
- production 每次切版本前先静止 API/Worker 并备份 PostgreSQL + objects；
- `RELEASE_COMPATIBILITY.json` 数据库代际不一致时，`rollback.sh` 会拒绝自动回退；
- WMA API Key 只通过 `/etc/deepaha/*.env` 注入，不进源码、ZIP、日志或迁移备份；
- SG8-A 本身未修改真实服务器，第一次宿主实机部署由 Codex 执行并先停在 staging 等待人工确认。

服务器脚本：`ops/sg8a/`。
