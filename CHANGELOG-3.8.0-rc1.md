# DeepAha 3.8.0-rc1 / SG8-A

基于 3.7.2-rc1 / SG7.2 的生产化版本。

## 新增

- PostgreSQL production/staging 发布体系；
- `migrate-sqlite-backup` 安全迁移本地正式数据；
- `deploy-check` 只读生产预检；
- staging/production systemd + Nginx 模板；
- 版本目录/current/previous 发布模型；
- quiesced PostgreSQL + objects 备份；
- 空目标恢复工具；
- 自动 HTTP Smoke 与同数据库代际代码回退；
- staging Basic Auth、production auth/API rate limit/HSTS 模板；
- 可选 PostgreSQL 本地服务器同构模拟 compose；
- Windows `export-sg8a-portable` 数据导出入口。

## 不变

- Direct WMA 协议；
- 一次整体审核；
- SG6.2 qualification compiler；
- SG4 Eligibility；
- SG5 Value/Priority；
- SG7.1 independent Gold Oracle；
- SG7.2 首页/关于我们/Logo；
- 正式事实权威边界。

## 数据库

本版本没有新增业务 schema 代际。SQLite → PostgreSQL 是部署介质迁移，不是事实模型变更。`database_generation` 仍为 `deepaha-product-v1-actionable2-actionloop1-lab2`。
