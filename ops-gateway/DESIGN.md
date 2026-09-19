# DeepAha Ops Gateway v1 — 设计与安全边界

## 1. 目标

让 ChatGPT 在**不获得 SSH / root Shell** 的前提下，执行少量、明确、可审计的 DeepAha 运维动作。

它解决的是“把服务器上的高风险自由操作，压缩成少数受控按钮”，不是建设通用远程管理平台。

## 2. v1 明确支持

### 只读

- `status`：DeepAha/Gateway 服务状态与最近操作；
- `logs`：只允许 gateway/api/web/worker，20–500 行；
- `operations`：查询异步操作历史与状态。

### 变更

- `deploy`：staging / production，仅完整 40 位 Git SHA；
- `backup`：固定环境备份；
- `rollback`：应用版本回退到 `previous` 或完整 SHA；
- `restart`：api/web/worker/all；
- `create_beta_user`：可选，由单独 `user_admin` scope 控制；若当前主项目没有稳定 CLI，服务器 adapter 必须返回 `NOT_IMPLEMENTED`。

## 3. v1 明确不支持

- 任意 Shell / SSH；
- `run_command`；
- 任意文件读取、下载或写入；
- 任意 systemd unit；
- 任意 journal unit；
- 任意 Git branch/tag/ref；
- 编辑 nginx、systemd、env、数据库；
- 数据库 restore；
- 删除备份；
- 修改防火墙；
- 安装软件包；
- root 文件浏览；
- 直接 SQL；
- 生产数据库回滚；
- 任何“传一条命令让我执行”的逃生口。

未来若确实需要新增能力，按**新增显式 action**的方式扩，不增加通用命令接口。

## 4. 信任边界

```text
ChatGPT / Connector
        │
        │ TLS + scoped bearer token
        ▼
Nginx / public endpoint
        │
        ▼
DeepAha Ops Gateway (deepaha-ops, non-root)
        │
        │ exact argv, no shell=True
        ▼
sudo -n /usr/local/sbin/deepaha-ops-adapter
        │
        │ root-owned, fixed action protocol, validates again
        ▼
Git / systemd / pg_dump / DeepAha CLI
```

关键原则：**Gateway 校验一次，adapter 再校验一次。** 即使 Gateway 出现参数校验缺陷，root 边界仍有第二道 allowlist。

## 5. 鉴权

- Bearer token 原文只保存于调用方安全凭据存储；
- Gateway 环境仅保存 SHA-256；
- 支持多 token、多 scope；
- scope：`read / deploy / backup / rollback / restart / user_admin`；
- 无 token → 401；scope 不足 → 403；
- 所有 mutation 还受 `DEEPAHA_OPS_MUTATIONS_ENABLED` 总开关保护，默认关闭。

## 6. 防误操作

### 不可变部署目标

只接受完整 Git commit SHA，不接受 `main`。这样部署动作永远可以精确复现和审计。

### 生产确认词

- production deploy：`DEPLOY_PRODUCTION`
- production rollback：`ROLLBACK_PRODUCTION`
- staging rollback：`ROLLBACK_STAGING`

确认词是服务器侧最后一道防误触，不替代产品侧“用户必须明确要求上线/回滚”的交互规则。

### 幂等

所有 mutation 必须带 `Idempotency-Key`。同一个 key 重试不会再次执行动作。

### 串行 mutation

v1 只有一个内部 mutation worker；部署、回滚、备份、重启不会并行执行。

## 7. 操作状态

mutation 返回 `202` 和 operation id：

```text
QUEUED → RUNNING → SUCCEEDED / FAILED
                   ↘ ABORTED（Gateway 重启时未完成）
```

调用方通过 `/v1/operations/{id}` 轮询，不需要让 HTTP 请求阻塞几分钟。

## 8. 审计

两层审计：

1. SQLite：操作、参数、状态、exit code、截断后的输出；
2. JSONL：操作排队/开始/结束、日志读取、状态读取等事件，并使用 `previous_hash + canonical_event` 形成 hash chain。

审计层会对常见 token/secret/password/API key/Authorization bearer 做脱敏。

## 9. 部署与回滚语义

### production deploy

adapter 必须：

```text
校验 SHA
→ production backup
→ 准备 release
→ migration
→ 切换应用版本
→ restart
→ health/smoke
```

如果 smoke 失败，可以切回 previous 应用版本；但 v1 **不自动恢复数据库**。如果 migration 已执行，必须在结果中显式记录数据库未回滚并停止自动动作。

### rollback

v1 rollback 是**应用回滚**。数据库恢复属于人工灾难恢复流程，不给 ChatGPT 一个“一键还原数据库”的按钮。

## 10. 为什么 Gateway 不直接知道服务器目录

Gateway 只认识固定 adapter 协议，真实服务器布局由 Codex 最后安装时绑定：

```text
Gateway（稳定）
   ↓
Adapter protocol（稳定）
   ↓
当前服务器 nginx/systemd/Git/目录/数据库方式（可变化）
```

这样未来 DeepAha 从“直接 checkout”迁移到“release symlink”，或者 systemd unit 改名，不需要改 ChatGPT 工具契约。

## 11. 网络边界

推荐：

- 独立 `ops.deepaha.com`；
- TLS；
- Uvicorn 只监听 `127.0.0.1:8765`；
- Gateway 不公开 `/docs`、`/redoc`、运行时 `/openapi.json`；
- Connector 使用仓库内静态 `openapi.yaml`；
- nginx body 限制 64 KiB；
- 能确认固定调用出口 IP 时再加 IP allowlist；不能确认时不要凭猜测写死。

## 12. v1 验收标准

工程验收：

- 无认证读取受保护接口 → 401；
- read token 无法 deploy → 403；
- `main` 作为 deploy ref → 422；
- production 无确认词 → 400；
- mutation 总开关关闭 → 503；
- 非 allowlist 日志服务 → 422；
- 日志超限 → 422；
- 同一 Idempotency-Key 不重复创建操作；
- Gateway restart 后遗留 QUEUED/RUNNING 不伪装成功；
- adapter 不使用 `shell=True`；
- production server 安装前 `mutations_enabled=false`。

生产安装验收另见 `install/CODEX_INSTALL.md`。
