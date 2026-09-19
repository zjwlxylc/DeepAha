# v0.2.0 增量接续：先读这一节

用户真正要求的是 **本地工具在后台调用 Codex CLI，从 ChatGPT 个人资料库自动取得资产包**，不是让用户手动下载后打开 Codex 操作工具。本版已在 v0.1.0 上增加该调用入口，不要再次误改需求。

新增：`codex_process.py`、`library_pull.py`、`library_window.py`；主窗口“从资料库获取”；CLI `library-list/library-fetch`。用户选择批次取回后，才回到原有预览/确认链路。

**本轮按用户要求未运行任何测试。旧 evidence/final_verification.* 和窗口截图仅属于 v0.1.0，不能拿来验收 v0.2.0。**当前状态见 `evidence/RELEASE_STATUS_v0.2.0.json`。

请先阅读 `docs/LIBRARY_PULL.md`，在用户本机核对：Codex 实际安装路径、CLI 参数、当前登录、实际可用资料库工具、原件导出方式与 JSONL 事件格式。不要猜测某个 MCP/插件一定提供原生 ChatGPT Library。不提供该能力就如实报告，不能以同名本地目录、Google Drive、摘要重建或手动下载冒充成功。

已有通道时，仅适配实际工具发现、事件和原件传递；不要删除请求/目录/ID/版本/原件检查，不要把退出码0或模型自述当成取得原件。使用最小权限配置，核对原始文件与本地字节，确认用户选中的目录和文件一致。

数据库接入仍按下方 v0.1.0 说明复用主仓。取文件、候选入库、来源批准是独立决定，不因新增 Codex 获取步骤而自动写库或启用 WMA。取消/失败不自动改成人工下载。

---

# v0.1.0 原接续说明（基础导入功能仍适用）

# 给 Codex 的接续开发说明

## 任务

在这份已可运行的导入源码上，完成与用户实际 DeepAha 的接入与真实环境验证。不要重新开发开放式来源探索，不迁移 Scout，不搭建第二套产品，不修改官网或 WMA 调查提示词。

先读：根目录 `README.md`、本文件、`docs/CONTRACT.md`、原始两份基线、`evidence/final_verification.json`。

## 已经实现，不必重做

本地中文窗口、CLI、严格 JSON/附件输入、候选及研究资产提取、签名预览、版本/去重/事务、受控 HTTP 传输、回执回读/恢复、可选的宿主批准接口、参考 SQLite/PostgreSQL 仓储和测试。

`scout_import_*` 是**研究暂存的参考实现**，不是声称主仓已有这些表。`PostgresRepository` 的程序实现存在，但未做真实 PostgreSQL 测试。`NoProductionAuthority` 是刻意的默认拒绝实现，不是“默认全部批准”。

## 接续顺序

### 1. 核对真实主仓，复用已有能力

在隔离工作分支读取现有 Source / Candidate / Brief / SourceIntelligenceRevision、身份/RBAC、应用服务、事务与迁移入口。确认真实命名和状态，不从历史聊天猜接口。

先记录“可直接复用 / 需要适配 / 确实缺失”，再以最小改动接入。已有来源与历史 ID 不重编号。不要不经核查把本包所有参考表复制成一套平行正式来源库。

### 2. 对接服务与存储

共享 `ImportService` 的业务逻辑。实现/适配 `repository.transaction(write=False/True)` 返回的事务接口；参考 `Transaction` 所需方法。将 source/brief/evidence/graph 等映射至现有研究资产模型；尚无结构的研究内容保留为有类型、有版本的资产。

原始 Handoff 字节、依赖文件、批次与回执必须原样保留。两种选择均可：小文件随应用数据库原子提交；或复用现有对象存储并按真实系统的暂存/确认机制保证一致性。不要把文件复制成功当数据库提交成功。

预览须只读；提交重验已确认包、环境、身份、动作与版本。SQLite 的 `BEGIN IMMEDIATE` 与 PostgreSQL 的元数据行锁是参考锁策略；主仓实际修订和人工审核的竞争写入也必须纳入适配策略。不能仅依赖 Python 进程锁。

### 3. 对接账户和受控 API

使用 `fastapi_adapter.create_router(service, get_principal)` 挂入原应用，或等价复用 `Router`。`get_principal` 从已验证的用户凭据得到服务器控制的 subject、producer、scopes；不能接收 Handoff 自报的身份。

能力最少为 `scout:preview`, `scout:import`, `scout:read`。只有有资格管理正式来源的身份才获 `scout:approve`。不让本地电脑持有任意数据库管理员凭据。

默认 API 路径是本次实现的协议路径 `/api/scout-import/v1`，**不是已确认在现网存在的地址**。宿主需要不同路径时同步客户端配置/适配，不去猜隐藏接口。

确认签名密钥由服务端安全配置，至少 32 随机字节，实例之间按部署政策共享并支持轮换；不写到本包、客户端或提示词里。生产入口 HTTPS，保留 TLS 校验，不开放通配 CORS，不使用参考 wsgiref 公开服务。

### 4. 保持正式来源批准隔离

第一版窗口默认只保存候选，通过现有 DeepAha 工作台批准/启用。没有批准时新来源不会进入 WMA 调度，新 Brief 也不替换生产有效版。

确需一次交互完成入库和来源批准，可实现 `AuthorityPort`，并通过 CLI/API 的独立 `approve_sources` 传入。必须在与导入相同的事务里记录人工身份、实际 Source ID、批准状态与有效 Brief。审核接入失败则整批回滚；不能在回调里先调用网络启动 WMA，再假装能回滚。

`resolve` 必须核对真实系统 ID 的组织/租户与授权，不可只按文本 UUID 存在就返回。`approve_in_transaction` 必须返回真实结果；接口文档在 `integration.py`。本轮没有伪造这个宿主实现。

不要通过简单地把 `reference_backend=True` 改成 False 来“通过”生产保护。只有实际完成原系统模型、认证、审批和事务适配、得到独立验证后才接 PRODUCTION。

### 5. 联调后再配置本地用户入口

Windows 原生验证 Python/Tk、中文路径、双击启动、字体/DPI、选择真实 Handoff、文件依赖、安全凭据、错误提示与回执目录。

连接真实测试服务验证全链，然后明确给用户服务地址、环境和登录/授权方式。密钥在本机或授权配置层填写，不要求用户发到聊天。

## 最低真实验收

有效真实包；重复批次；同键不同内容；数据库已有来源；旧版本/别名/入口迁移；缺证据/非法引用；未授权写入；预览后修改；并发；整批回滚；提交后断线并恢复回执；新来源不自动启用；已生效 Brief 不被候选覆盖；有权限的明确批准才生效；回执标注实际环境且能供 Scout 作为反馈读取。

候选导入不是对研究内容的事实核验。语法/引用通过不等于官方网址真实，也不等于资格事实已成立。

## 当前测试运行

```bash
python -m unittest discover -v
```

Linux 无桌面：`xvfb-run -a python -m unittest discover -v`。

仅在独立 PostgreSQL 测试库上，安装可选驱动，并在本机环境设置 `DEEPAHA_IMPORT_TEST_POSTGRES_DSN` 与 `DEEPAHA_IMPORT_TEST_ALLOW_SCHEMA=YES_ISOLATED_DATABASE` 后，运行 `tests.test_postgres_optional`。它会建立参考表和测试记录，不要指向生产库。

最终输出应区分：源码测试通过、Windows通过、真实测试库通过、生产部署未做/已授权完成。禁止把本包离线演练冒充真实生产验收。

## 可直接粘贴给 Codex 的任务

> 请读取本源码包的 README、docs/CODEX_HANDOFF.md、docs/CONTRACT.md 和 evidence/final_verification.json。基于已经实现的导入器代码，在实际 DeepAha 仓库先核对来源情报模型、事务与身份权限，再做最小接入，不重写整个工具，不新增系统内信源探索，不部署生产或写生产库。复用原系统数据与 ID，保持预览只读、人工确认、幂等、版本冲突、回执回读、候选不自动启用。先在隔离测试环境验证；完成后提供 Windows 双击入口的实际使用步骤及仍未验证项。
