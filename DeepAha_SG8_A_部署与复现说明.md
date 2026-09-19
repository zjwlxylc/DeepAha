# DeepAha SG8-A 部署与复现说明

版本：**3.8.0-rc1 / SG8-A**。

## 你本地先做什么

SG8-A 仍可像 SG7.2 一样在 Windows 本地运行。继续使用原数据目录：

`C:\Users\LENOVO\deepaha-data`

SG8-A 没有新增业务表，因此本地首次启动不会因为 SG8-A 额外改写正式机会数据，也不需要重新调用 WMA。

准备上服务器时，在 SG8-A 目录双击：

`scripts\export-sg8a-portable.cmd`

它会安全停止本启动器管理的本地 API/Worker，生成并验证一份迁移备份。该 ZIP **包含用户数据和密码哈希，是敏感文件；不包含 WMA API Key。**

## 服务器目标形态

- `staging.deepaha.com` → 127.0.0.1:8100 → staging PostgreSQL
- `www.deepaha.com` → 127.0.0.1:8000 → production PostgreSQL
- API/Worker：systemd
- Reverse proxy/TLS：现有 Nginx
- release：`/opt/deepaha/releases/3.8.0-rc1`
- data：`/var/lib/deepaha/staging|production`
- secret：`/etc/deepaha/staging.env|production.env`
- backup：`/var/backups/deepaha/...`

## 第一轮只部署 staging

把完整源码包和 portable backup 给 Codex。Codex 按 `docs/sg8_a/06_CODEX_DEPLOY_TASK.md` 执行。

只有你在 `staging.deepaha.com` 实际确认：

- 数据完整；
- 登录/权限正常；
- 机会总览/星图/行动正常；
- reviewer/operator 正常；
- SG7.1 Lab 正常；
- 手机正常；
- 备份校验正常；

才允许 Codex 切 `www.deepaha.com`。

## 后续升级

以后统一：

`本地改代码 → 自动测试 → staging → 你验收 → production backup → deploy → smoke`

不要再直接登录 production 修改源码。
