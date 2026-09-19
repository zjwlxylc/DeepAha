# SG8-A｜Public Beta 生产化底座

版本：**DeepAha 3.8.0-rc1 / SG8-A**  
基线：**3.7.2-rc1 / SG7.2**。

SG8-A 不重写机会生产、整体审核、资格判断、Value/Priority、Gold Benchmark 或数字实验室。它只解决一个新的工程问题：**把已经能在本地运行的真实产品，变成可以长期部署、验证、升级和回退的公网系统。**

## 交付目标

```text
Windows 本地开发 / SQLite
        ↓ 经过校验的 portable backup
PostgreSQL staging
        ↓ staging.deepaha.com 内部验收
PostgreSQL production
        ↓ www.deepaha.com Public Beta
```

同时建立以后每个版本都沿用的发布纪律：

```text
本地开发 → 自动测试 → staging → 人工验收 → 生产备份 → 发布 → Smoke → 可回退
```

## SG8-A 新增

- `migrate-sqlite-backup`：已校验本地 SQLite 备份 → 空 PostgreSQL + 原件目录；逐表内容指纹验证；不迁移 WMA 密钥；旧浏览器会话全部撤销。
- `deploy-check`：只读检查生产模式、PostgreSQL、schema/meta、活跃账号、数据目录和 WMA 配置，不发起 WMA 调查。
- `infra/sg8a/`：staging/production 环境模板、systemd 模板、Nginx 模板、可选 PostgreSQL 本地模拟 compose。
- `ops/sg8a/`：host preflight、bootstrap、备份、校验、空目标恢复、版本安装、HTTP Smoke、代码回退、Beta 用户创建。
- 版本化服务器目录：`/opt/deepaha/releases/<version>` + `staging-current / production-current`。
- 数据与代码分离：`/var/lib/deepaha/staging|production` 不放在 release 目录。
- 生产备份与代码回退分开：数据库代际不一致时禁止自动代码回退。

## 没有做的事情

- 没有连接或修改你的真实服务器；
- 没有修改 deepaha.com 的 DNS / Nginx / systemd；
- 当前容器没有 PostgreSQL/nginx/systemd 实机，因此这些宿主集成必须由 Codex 在实际服务器完成；
- 没有自动开放自助注册；Public Beta 第一批用户建议由 CLI 邀请创建；
- 没有额外调用 WMA；WMA Key/Agent ID 不进入源码包。

## 最重要的入口

- 服务器部署：`docs/sg8_a/03_SERVER_DEPLOYMENT.md`
- 本地数据迁移：`docs/sg8_a/02_DATA_MIGRATION.md`
- 后续升级/回退：`docs/sg8_a/04_RELEASE_ROLLBACK.md`
- 自测证据：`docs/sg8_a/05_VALIDATION.md`
- 给 Codex 的短任务：`docs/sg8_a/06_CODEX_DEPLOY_TASK.md`
