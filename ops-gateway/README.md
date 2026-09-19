# DeepAha Ops Gateway v1

DeepAha Ops Gateway 是给 ChatGPT/受控自动化使用的**最小权限运维入口**。它不是 SSH 替代品，不提供任意 Shell、任意路径、任意 systemd 服务名或任意 Git ref。

## v1 能力

- 读取 Gateway/DeepAha 状态
- 读取 API/Web/Worker/Gateway 的受限日志
- 部署 staging / production（仅接受完整 40 位 commit SHA）
- 备份
- 应用级回滚（默认不恢复数据库）
- 重启固定服务组
- 可选：创建 Beta 用户（独立 `user_admin` scope）
- 查询异步操作状态与最近操作

## 安全原则

1. **无任意命令执行**：Gateway 只调用一个 root-owned adapter，动作与参数均为 allowlist。
2. **默认只读**：`DEEPAHA_OPS_MUTATIONS_ENABLED=false` 是默认值，安装验证完成后才显式开启。
3. **不可变部署目标**：部署只接受完整 commit SHA，不接受 `main`、tag 或任意 branch。
4. **生产双确认**：production deploy / rollback 必须带固定 confirmation 字段；调用侧仍应只在用户明确要求后执行。
5. **最小权限 Token**：服务端只保存 token 的 SHA-256；可为 read/deploy/backup/rollback/restart/user_admin 分配不同 scope。
6. **串行变更**：所有 mutation 通过单 worker 串行执行，避免部署、回滚和重启互相踩踏。
7. **幂等**：所有 mutation 要求 `Idempotency-Key`；重复提交返回同一 operation。
8. **持久审计**：SQLite 保存操作状态；JSONL 审计日志使用 hash chain 并做常见 secret redaction。
9. **不暴露 OpenAPI**：生产服务关闭 `/docs`、`/redoc` 和 `/openapi.json`；连接器使用仓库内静态 `openapi.yaml`。
10. **Gateway 与业务 API 分离**：建议独立 systemd 服务，仅监听 `127.0.0.1:8765`，由 TLS 反向代理暴露。

## 本地开发

```bash
cd ops-gateway
uv sync --group dev
uv run pytest
uv run ruff check .
```

生成一个高熵 Token，再只把哈希写入服务器配置：

```bash
TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
printf '%s' "$TOKEN" | sha256sum
```

环境变量示例：

```bash
DEEPAHA_OPS_MUTATIONS_ENABLED=false
DEEPAHA_OPS_ADAPTER_PATH=/usr/local/sbin/deepaha-ops-adapter
DEEPAHA_OPS_ADAPTER_USE_SUDO=true
DEEPAHA_OPS_STATE_DIR=/var/lib/deepaha-ops
DEEPAHA_OPS_AUDIT_LOG=/var/log/deepaha-ops/audit.jsonl
DEEPAHA_OPS_TRUSTED_HOSTS=ops.deepaha.com,localhost
DEEPAHA_OPS_TOKEN_HASHES_JSON={"<sha256>":["read","deploy","backup","rollback","restart"]}
```

## 服务器适配器协议

Gateway 不知道服务器内部部署细节。Codex 最终安装时只需实现 root-owned：

`/usr/local/sbin/deepaha-ops-adapter`

固定协议：

```text
status
logs <gateway|api|web|worker> <20..500>
deploy <staging|production> <40-char-sha>
backup <staging|production>
rollback <staging|production> <previous|40-char-sha>
restart <api|web|worker|all>
create-beta-user <username> <email>
```

adapter **不得**把参数拼进 `sh -c` / `eval`，必须再次做 allowlist 校验。生产 deploy 应在 adapter 内强制先备份，再部署、迁移、health/smoke；失败时只能做应用级回退，数据库恢复不属于 v1 自动动作。

## 安装

见 `install/CODEX_INSTALL.md`。正式服务器安装与现有 nginx/systemd/目录对齐由 Codex 最后执行。
