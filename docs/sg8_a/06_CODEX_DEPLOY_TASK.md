# 给 Codex 的服务器部署任务（短版）

> 使用我提供的 `DeepAha_Rebuild_3.8.0-rc1_SG8_A.zip`，不要改业务代码。先只读检查服务器当前 deepaha.com 的 Nginx/systemd/目录/PostgreSQL 状态并备份现有原型。按包内 `docs/sg8_a/03_SERVER_DEPLOYMENT.md` 和 `ops/sg8a/` 执行：建立 staging/production 发布目录和 systemd，创建独立 PostgreSQL 库，先把我的本地 portable backup 迁到 `staging.deepaha.com`，完成 deploy-check、HTTP Smoke、权限/数据核对并把结果告诉我。**未得到我确认前，不切换 www.deepaha.com，不删除旧原型，不修改 SG8-A 源码。**
