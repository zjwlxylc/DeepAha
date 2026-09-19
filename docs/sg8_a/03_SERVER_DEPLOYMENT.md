# SG8-A｜服务器首次部署

## 0. 原则

先 `staging.deepaha.com`，后 `www.deepaha.com`。不要直接覆盖当前交互原型。

## 1. 宿主预检

解压 SG8-A 后：

```bash
bash ops/sg8a/preflight-host.sh
```

需要 Python 3.13、Nginx、systemd、PostgreSQL client tools、curl、tar 等。缺什么先补什么，不要继续部署。

## 2. 一次性 bootstrap

```bash
sudo bash ops/sg8a/bootstrap-host.sh
```

只创建系统账号、目录和 systemd 模板；不会改现有 deepaha.com Nginx，也不会创建数据库或凭据。

## 3. 环境文件

分别从：

- `infra/sg8a/staging.env.example`
- `infra/sg8a/production.env.example`

复制到：

- `/etc/deepaha/staging.env`
- `/etc/deepaha/production.env`

权限：`640 root:deepaha`。

真实 DB 密码和 WMA Key 只放这里，不进入源码、Git、部署命令参数或 Nginx。

## 4. PostgreSQL

创建两个独立数据库/账号，例如：

- `deepaha_staging`；
- `deepaha_prod`。

账号仅拥有自己数据库的必要 DDL/DML 权限，不用 PostgreSQL 超级用户运行应用。

## 5. 数据迁移

按 `02_DATA_MIGRATION.md` 先把本地备份迁入 staging。

## 6. 部署 staging

```bash
sudo bash ops/sg8a/install-release.sh staging /path/to/extracted-sg8a \
  --sqlite-backup /secure/path/DeepAha-local-....zip
```

如果 DB 已经初始化，以后升级不再传 `--sqlite-backup`。

`install-release.sh` 会：

1. 复制到 `/opt/deepaha/releases/3.8.0-rc1`；
2. 建独立 venv + 安装 PostgreSQL 运行依赖；
3. compileall；
4. `deploy-check`；
5. 已有环境先做 quiesced PostgreSQL + objects backup；
6. 原 current 保存到 previous；
7. 切 current symlink；
8. restart systemd；
9. 本机 `/health/live /ready /` Smoke；
10. Smoke 失败自动恢复旧代码指针。

## 7. staging Nginx

参考 `infra/sg8a/nginx/deepaha-staging.conf.example` 合并到服务器现有配置。先准备：

- `staging.deepaha.com` DNS；
- TLS；
- `/etc/nginx/.htpasswd-deepaha-staging`。

然后 `nginx -t` 成功才 reload。

## 8. 人工验收

至少验证：

- 首页/关于我们；
- 登录；
- 普通 user 无工作台权限；
- reviewer/operator 权限隔离；
- 机会总览、详情、星图、行动；
- SG7.1 Opportunity Lab；
- 手机访问；
- 服务器重启后 systemd 自启；
- backup + verify；
- WMA 配置如果启用，只做一例明确授权 Smoke。

## 9. production

staging 人工验收通过后，再以独立 `deepaha_prod` 数据库重复迁移/部署。Nginx 切换前备份现有原型配置和原型目录。

建议把旧原型保留在 `prototype.deepaha.com` 或离线归档，而不是直接删除。
