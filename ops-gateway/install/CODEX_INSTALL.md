# DeepAha Ops Gateway v1 — Codex 最终服务器安装任务

> 本文只用于用户明确要求“开始安装”之后。不要在未获授权时连接或修改生产服务器。

## 目标

把仓库 `ops-gateway/` 安装成独立的 `deepaha-ops-gateway.service`，只监听 `127.0.0.1:8765`，由现有 HTTPS nginx 反代；实现并安装 root-owned `/usr/local/sbin/deepaha-ops-adapter`，让 Gateway 获得**固定 allowlist 运维动作**，而不是 shell 权限。

## 不得改变的安全边界

- 不增加 `exec` / `shell` / `run_command` / 任意路径读写接口。
- Gateway 进程不得以 root 运行。
- adapter 必须 root:root，0755 或更严格；`deepaha-ops` 用户不可写。
- mutation 默认关闭；安装 smoke 全通过后，用户明确同意再设置 `DEEPAHA_OPS_MUTATIONS_ENABLED=true`。
- deploy 只接受 40 位 commit SHA；服务器 adapter 再次验证。
- production deploy 必须先备份数据库/关键配置元数据，再部署；不得自动做数据库 restore。
- rollback v1 只做应用版本回退，不做数据库回滚。需要数据库恢复时停止并交人工。
- 日志只允许 gateway/api/web/worker，最多 500 行；不得暴露 `/etc`、env 文件或任意 journal unit。
- Token 原文只进入 ChatGPT Connector/安全凭据存储；服务器只保存 SHA-256 哈希。

## S0 只读盘点

先只读确认：

1. 当前代码目录与 Git 部署方式；
2. 当前 `deepaha` 相关 systemd unit 名称；
3. nginx TLS vhost 与域名结构；
4. API/Web/Worker 实际健康检查地址；
5. PostgreSQL 备份方式、数据库连接凭据如何安全取得；
6. 当前 migration 命令；
7. staging 是否存在；若不存在，不要虚构，记录 `STAGING_NOT_PRESENT`；
8. 当前发布回滚点如何识别。

把盘点写入 `/root/deepaha-ops-install-evidence/S0.md`，不得修改服务。

## S1 安装 Gateway（mutation 关闭）

- 创建系统用户 `deepaha-ops`，无登录 shell。
- 安装 `ops-gateway/` 到 `/opt/deepaha/ops-gateway`，建立独立 venv。
- 创建 `/var/lib/deepaha-ops`、`/var/log/deepaha-ops`，所有者 `deepaha-ops`，权限 0700。
- 创建 `/etc/deepaha-ops/gateway.env`，root:deepaha-ops，0640。
- 生成至少两个高熵 token：read token 与 mutate token。只把 SHA-256 写入 `DEEPAHA_OPS_TOKEN_HASHES_JSON`；原 token 放入用户指定的安全凭据位置，不出现在日志/Markdown/终端回显中。
- 安装 systemd unit，先保持 `DEEPAHA_OPS_MUTATIONS_ENABLED=false`。

验证：

- localhost `/health` → 200；
- 无 token `/v1/status` → 401；
- read token `/v1/status` → 正常；
- mutation → `MUTATIONS_DISABLED`。

## S2 实现服务器 Adapter

基于 S0 的真实部署结构实现 `/usr/local/sbin/deepaha-ops-adapter`。不要简单复制 reference adapter 的 mutation stub。

必须支持：

```text
status
logs <gateway|api|web|worker> <20..500>
deploy <staging|production> <sha>
backup <staging|production>
rollback <staging|production> <previous|sha>
restart <api|web|worker|all>
create-beta-user <username> <email>
```

如果当前 DeepAha 没有稳定的 beta-user CLI，`create-beta-user` 必须返回明确 `NOT_IMPLEMENTED`，不要直接写数据库。

### deploy 必须至少执行

1. 校验 SHA；
2. 验证 SHA 存在于允许的 GitHub 仓库；
3. production 前执行 backup；
4. 构建/安装目标 release；
5. 运行当前仓库规定的 migration；
6. 切换应用版本；
7. 重启必要服务；
8. health + smoke；
9. 记录 deployed SHA。

如果 smoke 失败：允许回退应用代码到 previous；**不得自动恢复数据库**。记录 `DB_MIGRATION_NOT_ROLLED_BACK`（如适用）并停止。

## S3 sudoers 与 nginx

- 通过 `visudo -cf` 验证 sudoers。
- nginx 使用专用 `ops.deepaha.com` TLS vhost 时，将请求反代到 `127.0.0.1:8765`。
- 如果实际只能使用路径前缀，必须同步修改静态 `openapi.yaml` 的 server URL，不能让 Connector 契约和真实路由不一致。
- 不暴露 systemd socket、目录索引、静态 state/audit 文件。
- `nginx -t` 通过后才 reload。

## S4 真实 Smoke（仍不做 production deploy）

至少验证：

- status；
- logs 上限与 allowlist；
- restart 一个非关键 staging 服务（若 staging 存在）；
- backup staging（若 staging 存在）；
- 错误 service/错误 SHA/缺确认词全部 fail closed；
- audit log 产生且没有 token 原文；
- 重复 Idempotency-Key 不重复执行。

若没有 staging，则不得用 production 替代“为了测试”。记录无法执行项。

## S5 开启 mutation

只有 S0–S4 无 P0/P1，且用户明确批准后，才把 `DEEPAHA_OPS_MUTATIONS_ENABLED=true` 并重启 Gateway。

## 最终交付

输出：

- 实际安装路径、unit、nginx route；
- Gateway commit SHA；
- adapter SHA256；
- 已验证动作与未验证动作；
- mutation 是否开启；
- staging 是否存在；
- production deploy **不要在安装任务里顺便执行**，除非用户另行明确要求上线某个 SHA。
