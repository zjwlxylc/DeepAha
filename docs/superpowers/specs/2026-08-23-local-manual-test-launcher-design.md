# DeepAha 本地人工测试一键启停设计

日期：2026-08-23
状态：已由用户确认，待实现与工程验证

## 目标与证据边界

在 Windows 独立工作树中提供清晰命名的双击启动、停止入口。启动入口负责检查本机依赖、启动隔离 PostgreSQL 与 S3 兼容服务、执行数据库迁移、准备许可安全的合成数据和临时身份、启动 API 与 Web，并打开已经带有会话的 Chromium。停止入口只终止本轮启动器可验证拥有的进程和 Compose 资源。

该环境仅用于本地人工使用和人工工程测试。真人参与者保持 `0`，Phase 6–8 Release Qualification 不因本功能改变，发布决定保持 `HOLD_MISSING_HUMAN_EVIDENCE`，提醒投递目标只允许 `TEST_INBOX`。

## 方案选择

采用一个专用 PowerShell 编排器、两个薄 `.cmd` 入口、一个专用 Compose 文件、一个组合合成种子器和一个 Playwright 浏览器宿主。它复用现有 Phase 6/7 个人与审核夹具、Phase 8 截止变化与 `TEST_INBOX` 夹具，不复制生产业务逻辑。

不直接调用 Phase 7/8 verifier：verifier 会在验证完成后销毁环境，两个 seed 也锁定不同数据库端口。不上线 Web 本地登录捷径：避免新增认证路由和攻击面。

## 运行拓扑

- Compose project：`deepaha-local-manual-<工作树路径哈希>`，必须匹配固定正则。
- PostgreSQL：仅绑定 `127.0.0.1:55439`。
- Moto S3：仅绑定 `127.0.0.1:55007`。
- FastAPI：仅绑定 `127.0.0.1:8009`。
- Next.js：仅绑定 `127.0.0.1:3089`。
- 运行目录：仓库内 `.deepaha-local-manual/`，加入 `.gitignore`。

启动顺序固定为：前置检查 -> 端口与既有状态检查 -> 依赖同步 -> Compose up/wait -> Alembic upgrade -> 组合 seed -> Web build -> API/Web 子进程 -> readiness -> Chromium -> 写入运行清单。所有阶段显示中文状态。

## 合成数据与身份

组合 seed 只接受精确的 `127.0.0.1:55439/deepaha` 空数据库：

1. 复用 Phase 6 固定机会、合成个人用户、画像和个人排序，生成个人会话。
2. 复用 Phase 7 reviewer 模型生成本轮随机审核会话；个人 Cookie 与 reviewer Cookie 使用不同名称。
3. 复用 Phase 8 截止变化夹具生成另一合成用户及 `TEST_INBOX` 投递。

浏览器宿主创建两个隔离浏览器上下文（Browser Context）：主上下文持有 Phase 6/7 个人与 reviewer Cookie，打开公开机会、个人行动和审核队列；提醒上下文只持有 Phase 8 个人 Cookie，打开提醒测试收件箱。明文临时凭证只保存在被忽略的运行目录，启动后浏览器读取完成即删除；数据库只保存摘要。

## 精确所有权与停止

运行清单记录规范化项目根、根路径 SHA-256、Compose project、Compose 文件、启动时间，以及 API、Web、浏览器宿主的 PID、创建时间、命令类别和日志路径。

停止前必须验证：

- 运行清单项目根等于当前脚本根；
- Compose project 与当前根哈希一致；
- 容器标签的 project、working directory 和 config file 与运行清单一致；
- 每个进程 PID 仍存在，创建时间匹配，命令行包含当前工作树和预期入口。

只对通过验证的进程树按子到父顺序执行 `Stop-Process`。不按端口找进程、不使用 `taskkill`、不执行 `docker system prune`。Compose 清理只使用精确 project 和 file 执行 `down --volumes --remove-orphans`。验证失败的对象只报告，不终止。启动中任一步失败时调用同一精确清理流程，并保留脱敏日志供排查。

## 用户体验与失败恢复

启动窗口使用中文阶段提示和最终入口说明，不显示端口、环境变量或令牌作为用户操作要求。缺少 Docker Desktop、uv、Node 24、Corepack，Docker daemon 未启动，或端口被未知监听占用时，在创建资源前失败并给出中文修复建议。

重复启动时，如果运行清单和服务健康均匹配，则只重新打开浏览器；若存在不完整或不匹配状态，则拒绝覆盖并提示先运行停止入口。停止可重复执行；没有运行状态时给出“无需停止”，不做全局扫描。

## 精确文件范围

创建：

- `启动 DeepAha 本地人工测试.cmd`
- `停止 DeepAha 本地人工测试.cmd`
- `scripts/local-manual-test.ps1`
- `scripts/tests/local-manual-test.Tests.ps1`
- `infra/compose.local-manual.yaml`
- `backend/tests/manual/__init__.py`
- `backend/tests/manual/seed_local_manual.py`
- `backend/tests/manual/test_seed_local_manual.py`
- `web/scripts/open-local-manual-browser.mjs`
- `docs/development/local-manual-testing.md`

修改：`.gitignore`、`README.md`、`scripts/verify.ps1`。除非红灯测试证明必要，不修改生产 API、Web 路由或现有 Phase verifier。

## 成功标准

- 双击等价启动能在干净状态完成迁移、合成种子、服务就绪和自动开页。
- 公开机会、个人画像/机会/行动、反馈提交/审核以及 Phase 8 `TEST_INBOX` 可供人工操作。
- 端口冲突、前置依赖缺失和重复/残缺状态均产生可理解的中文失败，且没有误清理。
- 双击等价停止只清理精确拥有的进程、容器、网络、卷和临时身份文件，四个专用端口释放。
- PowerShell 定向测试、后端 seed 单元/集成测试、根验证、Phase 8 风险相称回归和实际启停烟雾验证通过。
- 不运行 Phase 2 live 观察，不创建自动化，不连接真实推送，不生产部署，不提交或推送。
