# Phase 1 测试摘要

## 当前工作副本

- 验证时间：`2026-08-21T20:25:18+08:00` 至 `2026-08-21T20:26:18+08:00`
- 实现提交：`c05b7d531190eeebffa6ebca4d35278cdc0788fa`
- uv：`0.12.5`
- Python：`3.14.7`
- Ruff：`0.16.4`
- mypy：`1.20.2`
- pytest：`9.1.1`
- Alembic：`1.19.1`
- Node.js：`24.14.0`
- pnpm：项目锁定 `10.15.0`
- Docker Engine：`29.6.1`
- PostgreSQL：`18.4`，镜像 `postgres:18.4-alpine3.23`
- 本地 S3：Moto `5.2.2`，镜像 `motoserver/moto:5.2.2`

## 自动验证结果

| 区域 | 命令 | 实际结果 |
| --- | --- | --- |
| Diff | `git diff --check` | 退出码 0；只有 Git 的 LF/CRLF 提示，无空白错误 |
| 后端快速基线 | `uv run pytest --strict-markers` | 退出码 0；`25 passed, 31 deselected` |
| 根验证 | `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` | 退出码 0；Ruff 格式/Lint、mypy 35 个源文件、后端快速测试、Web Lint/类型/1 个测试/生产构建全部通过 |
| Phase 1 迁移 | `uv run alembic upgrade head` | 退出码 0；应用 `20260821_0001` |
| Phase 1 集成 | `uv run pytest -m integration --strict-markers` | 退出码 0；`31 passed, 25 deselected` |
| 迁移漂移 | `uv run alembic check` | 退出码 0；`No new upgrade operations detected.` |
| Phase 1 入口 | `powershell -ExecutionPolicy Bypass -File scripts/verify-phase1.ps1` | 退出码 0；根验证、服务启动、迁移、集成、漂移检查和范围化清理全部完成 |
| CI YAML | PyYAML 读取 `.github/workflows/ci.yml` 并断言作业/镜像 | 退出码 0；识别 `backend-quality`、`web-quality`、`integration` 三个作业及固定 PostgreSQL/Moto 镜像 |

## 故障注入

临时把官方 fixture 期望 SHA 的最后一位由 `b` 改为 `c` 后运行 `scripts/verify-phase1.ps1`：脚本退出码为 `1`，集成结果为 `2 failed, 29 passed, 25 deselected`，失败包含精确 SHA 断言。`finally` 删除了 `deepaha-phase1-27284` 项目的 PostgreSQL、Moto 容器和网络。恢复正确 SHA 后同一脚本退出码为 `0`。

## 新鲜副本

- 路径：`C:\Users\LENOVO\AppData\Local\Temp\DeepAha-Phase1-Gate-c05b7d5`
- 开始时间：`2026-08-21T20:36:58.6666641+08:00`
- 结束时间：`2026-08-21T20:39:15.5071317+08:00`
- 源提交：`c05b7d531190eeebffa6ebca4d35278cdc0788fa`
- 操作系统：Microsoft Windows 11 家庭版 `10.0.26200`，构建 `26200`
- 工具：uv `0.12.5`、Python `3.14.7`、Ruff `0.16.4`、mypy `1.20.2`、pytest `9.1.1`、Alembic `1.19.1`、Node.js `24.14.0`、pnpm `10.15.0`、Docker Engine `29.6.1`、PostgreSQL `18.4`
- 验证前：`.venv`、`node_modules`、`.next`、数据库文件和对象目录均不存在；Schema 文件 CRLF 对为 0；固定 fixture 为 11,662 字节和批准 SHA。
- `scripts/verify.ps1`：退出码 0；新建 `.venv` 并安装 58 个 Python 包，安装 445 个 Web 包，Ruff/mypy 通过，`25 passed, 31 deselected`，Web `1 passed` 且构建成功。
- `scripts/verify-phase1.ps1`：退出码 0；集成为 `31 passed, 25 deselected`，应用 revision `20260821_0001`，`alembic check` 无新增操作，专属容器与网络删除。
- 验证后：Git 状态仍干净；没有名为 `deepaha-phase1-*` 的运行中容器。

第一次从 `8cfa30f…` 创建的新鲜克隆曾因 Windows 自动换行导致确定性 Schema 字节测试失败；旧根脚本又错误返回 0。该失败没有被写成 PASS。提交 `c05b7d5…` 增加 Git 属性并让根脚本逐命令传播非零退出；故障探针证明 pytest 失败时脚本退出 1 且不进入 Web，随后上述第二个新鲜克隆完整通过。

## 远程持续集成

尚未 push，也没有当前 Gate 提交的 Actions run URL 或 job conclusions。`backend-quality`、`web-quality` 与新增 `integration` 的远程结论均为待获取。

## 范围与秘密扫描

- `git diff --stat 22f11b8e99311067670d8bbf1394fb881bf7e872..HEAD`：52 个文件，5,204 行新增、9 行删除；逐项属于 Phase 1 设计/计划、契约、迁移/ORM、对象存储、固定样本、测试、验证或相应文档。
- 跟踪文件中的 `.env`、数据库/SQLite、`node_modules`、`.next`、`.venv`、`__pycache__`、对象和 data 目录匹配数：0。
- `AKIA` 与私钥头匹配数：0。
- PostgreSQL 凭据形态匹配数：9。逐条为 CI/脚本的 `127.0.0.1` 一次性常量、测试值或计划代码块（其中一条是扫描命令自身）；无外部数据库主机或真实凭据。
- 当前工作树没有数据库文件、对象内容、缓存或构建产物；两张主工作区用户图片不在本分支 worktree 中，也未被触碰。
