# DeepAha 当前开发入口

## 最新正式站交付（2026-09-20）

继续开发或部署前先读 `docs/beta-access/UI_COPY_CLEANUP.md`（最新正式发布）及 `docs/beta-access/PUBLIC_RELEASE.md`（账号功能首次发布历史）。用户已人工验收，最新正式源码9149e03f，含用户端文案精简、生日输入与本地启动升级修复。正式服务仍命名为staging/8100，指针staging-current。staging域名独立使用staging-isolated/8200，保持d32082ad版本及Basic Auth。发布前仍需实机复核。

当前交付：**3.8.0-rc1 / SG8-A Public Beta 生产化底座**。

基线：**3.7.2-rc1 / SG7.2**。SG8-A 只增加部署、PostgreSQL迁移、备份、staging/production、发布与回退能力；SG1–SG7.2 的正式业务核心继续冻结。

先读：

- `docs/sg8_a/00_START_HERE.md`
- `docs/sg8_a/02_DATA_MIGRATION.md`
- `docs/sg8_a/03_SERVER_DEPLOYMENT.md`
- `docs/sg8_a/04_RELEASE_ROLLBACK.md`
- `docs/sg8_a/05_VALIDATION.md`
- `docs/sg8_a/06_CODEX_DEPLOY_TASK.md`
- `README.md`

产品入口：`deepaha.main:app`；业务模块 `deepaha.product`；前端 `web/public/product`。

## 绝对业务边界

- reviewer 仍只做整体通过/不通过；不恢复逐字段人工审核。
- WMA 只生产 Candidate Facts，不批准 VerifiedFact / Rule / Eligibility。
- SG6.2 `INELIGIBLE` 证据纪律保持不变。
- SG7 Lab 不能回写生产 Opportunity、Eligibility、Ranking、Rule 或审核决定。
- Synthetic Twins 永远不能冒充真实用户证据。
- Eligibility truth 与 Recommendation truth 分开。
- SG8-A 部署工具不能自动批准 Source/Opportunity，也不能通过数据库迁移改变审核含义。
- WMA API Key 只允许通过宿主 `/etc/deepaha/*.env` 注入；源码、迁移包、日志、ZIP禁止包含真实密钥。
- 服务器 production 源码禁止在线编辑；修改必须回到本地代码基线。
- 未经 staging 人工确认，不允许切换 `www.deepaha.com`。

## 必跑验证

- `backend/tests/product` 全业务回归，每个测试文件独立 RC=0；
- `python -m compileall -q backend/src backend/tests/product`；
- product / SG7.2 前端契约；
- SG7.1 两套 independent Gold Oracle；
- SG8-A SQLite backup typed-copy migration harness；
- SG8-A env/systemd/nginx/compose/script 静态契约；
- 本地真实 HTTP `/health/live /ready /` Smoke；
- 最终包真实 WMA Key/Agent ID 精确 0 命中。

## 宿主实机 Gate

当前容器没有 PostgreSQL server、Nginx 或 systemd 可用实例，因此真实宿主 Gate 只能由 Codex 在服务器 staging 执行：PostgreSQL 迁移、systemd、Nginx/TLS、backup/restore drill、WMA server binding。任何一项未通过都不得切 production。
