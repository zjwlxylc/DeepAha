# SG8-A 环境与发布架构

## 1. 三层环境

### Local
继续保留 `启动机会星图.cmd` + SQLite，适合开发、回归和人工查看。SG8-A 没有把本地开发强制改成 PostgreSQL。

可选的服务器同构模拟位于 `infra/sg8a/compose.dev.yaml`，用于有 Docker 条件时在本地提前验证 PostgreSQL 容器路径。

### Staging
- 域名：建议 `staging.deepaha.com`；
- API：`127.0.0.1:8100`；
- 独立 PostgreSQL 数据库；
- 独立 `/var/lib/deepaha/staging`；
- Nginx 额外 Basic Auth；
- 默认 `PUBLIC_CATALOG=0 / ALLOW_REGISTRATION=0 / WMA_ENABLED=0`。

### Production
- 域名：`deepaha.com / www.deepaha.com`；
- API：`127.0.0.1:8000`；
- 独立 PostgreSQL 数据库；
- 独立 `/var/lib/deepaha/production`；
- 公网只暴露 Nginx 443/80，API 端口只监听 loopback；
- 自助注册默认关闭，第一批 Beta 用户由 `create-beta-user.sh` 创建。

## 2. 服务器目录

```text
/opt/deepaha/
  releases/
    3.8.0-rc1/
    ...
  staging-current -> releases/...
  staging-previous -> releases/...
  production-current -> releases/...
  production-previous -> releases/...

/etc/deepaha/
  staging.env
  production.env

/var/lib/deepaha/
  staging/
    objects/
  production/
    objects/

/var/backups/deepaha/
  staging/<timestamp>/
  production/<timestamp>/
```

**代码可以切换，数据目录不能跟着 release 删除。**

## 3. systemd

使用模板单元：

- `deepaha-api@staging.service`
- `deepaha-worker@staging.service`
- `deepaha-api@production.service`
- `deepaha-worker@production.service`

服务读取 `/etc/deepaha/%i.env`，以 `deepaha` 非登录系统账号运行，`ProtectSystem=strict`，仅 `/var/lib/deepaha/%i` 可写。

## 4. Nginx

Production 模板增加：

- TLS/HSTS；
- auth/login/register 限流；
- API 通用限流；
- 上传体积边界；
- 只代理到 `127.0.0.1:8000`。

Staging 额外使用 HTTP Basic Auth，避免 staging 本身成为第二个公开站点。

## 5. 数据库与事实权威

SG8-A 只改变数据库运行介质，不改变 DeepAha 的事实权威边界：

```text
WMA Candidate / Artifact
        ↓
整体人工审核
        ↓
正式 Opportunity / Publication
        ↓
Eligibility / Value / Priority
```

PostgreSQL 不能让 WMA 获得发布权限；部署脚本也不会自动批准任何机会。

## 6. 可选本地 PostgreSQL 同构模拟

如果你的 Windows 电脑以后安装 Docker Desktop，可以在真正服务器部署前额外跑一层 PostgreSQL 模拟：

```powershell
cd infra\sg8a
Copy-Item .env.sg8a-dev.example .env.sg8a-dev
# 修改本地开发密码（只用于本机）
docker compose -f compose.dev.yaml up -d postgres
docker compose -f compose.dev.yaml run --rm api python -m deepaha.product.cli setup
docker compose -f compose.dev.yaml up -d api
```

访问 `http://127.0.0.1:18000`。

这套模拟**不是必须条件**。正常 Windows 开发仍可继续使用 SQLite；它的作用只是让需要时能提前复现 PostgreSQL 容器路径。

本次构建环境没有 Docker daemon，因此 compose 只完成 YAML/契约静态检查，没有冒充“容器已经实际启动”。
