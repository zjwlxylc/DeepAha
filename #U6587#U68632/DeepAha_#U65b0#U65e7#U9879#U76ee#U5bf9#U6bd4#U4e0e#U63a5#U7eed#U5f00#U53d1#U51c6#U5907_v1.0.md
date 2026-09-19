# DeepAha 新旧项目对比分析与接续开发准备

日期：2026-09-17
性质：基于两个目录的实际文件、git 记录、文档与实际运行测试的核查报告。凡标注「本次实测」的结论均由本机实际执行得到；凡来自交付文档的结论均标注来源文件，未重复执行的不冒充已验证。

---

## 0. 一页结论

| 问题 | 结论 |
|---|---|
| 旧项目为什么失败 | 不是代码不能跑（本次实测仍可导入，11 条路由），而是**方向性失败**：把「逐字段事实核验 → 方法认证 → 规则批准」设成了内容收录的前置，导致「拿到结果就能用」永远到不了；叠加 WMA 原件回收损坏却机械检查报 OK、真人参与者为 0、80 个并行分支互相冲突。 |
| 新项目现在是什么 | 3.0.0-rc2 重建候选版：**可启动、有真实数据库与真实 API 的产品闭环**，主链已通（来源 → 导入 → 原件 → 投影 → 一次整体决定 → 总览 → 个人行动）。不是生产已部署版本。 |
| 新项目实测状态 | 后端 76 通过 / **2 失败**（文档声称 78 通过）；前端检查通过。2 个失败同源，是 Windows 平台缺陷，不是业务逻辑错误。 |
| 最大缺口 | 真实 WMA 调用、PostgreSQL、原生浏览器、Windows 实机、原数据库迁移、通知渠道、支付——全部 NOT_RUN / NOT_CONNECTED，且都是「环境不具备」而非「代码没写」。 |
| 下一步最该做的 | 先修 Windows 备份缺陷（P0-1），再补真实 WMA 与 PG 副本验证（P1），最后才是功能扩展。不建议再发起一轮重构。 |

---

## 1. 旧项目 D:\DeepAha

### 1.1 目标

产品定位（README）：**DeepAha 青年机会智能系统 / 机会星图**——把分散、变化、复杂的机会信息转化为可理解、可判断、可行动的路径。

三类角色：普通用户（发现机会、画像匹配、行动、反馈）、审核员（事实/规则裁决）、系统/数据管理员（来源、采集、任务、发布）。

商业化主线（`文档/DeepAha_后续开发路线图与阶段门_v1.2.md`）明确为五个必须跨过的门：真实来源门、真实质量门、完整产品门、真实价值门、商业成立门；对应阶段 P10 → P11 → P12 → P13 → P14，并规定「任何阶段未通过，不得用扩大来源、增加页面、增加 AI 聊天、宣传包装或提前收费来掩盖」。

### 1.2 已有实现

技术栈：Python 3.14 + FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL 18 + S3(moto) + Pydantic；前端 Next.js 16 / React 19 / TypeScript / pnpm。

规模（本次统计，排除依赖目录）：

- 后端 `backend/src/deepaha/` 共 **389 个 .py、40,772 行**，分 22 个模块
- 前端 `web/app` 41 个 .tsx 页面；`web/node_modules` 已安装
- 后端测试 **173 个 test_*.py**
- Alembic 迁移 26 个文件（25 条 down_revision 链）
- Git：185 个提交、**80 个分支**；最后一个代码提交 `d806e30` 于 **2026-08-26**

主要模块行数（本次统计）：

| 模块 | 行数 | 作用 |
|---|---|---|
| p9b | 7,244 | AI 能力层：模型网关、Provider 适配器、出口管控、调用账本、事实链/文档块/资格 |
| local_human_test | 4,901 | 本地人工测试控制台、受控 Provider、抽取与发布（**已被新项目列为待退役**） |
| contracts | 4,536 | 领域契约与 schema |
| acquisition | 3,609 | 采集控制平面、策略、官方证据保全 |
| opportunities | 2,512 | 机会身份、版本、变更 |
| api | 2,308 | 路由装配 |
| documents / notifications | 1,911 / 1,892 | 文档与证据块；提醒 Outbox/租约/幂等 |
| personal | 1,934 | 画像、匹配、个人行动 |
| sources / review | 1,578 / 1,404 | 来源注册表；审核服务 |
| artifacts | 741 | 对象存储（**被新项目实际复用**） |
| 其余（eligibility/rules/validation/feedback/evaluation/public_catalog/db/matching/profiles/core） | 约 4,300 | 资格、规则、校验、反馈、公开目录等 |

工程门状态（README 原文）：Phase 1 历史 Gate CLOSED；Phase 2–8 均为 IMPLEMENTED、Engineering Gate CLOSED。

### 1.3 失败原因（按证据强度排列）

**（1）发布资格始终未成立——最根本的失败。**
README 自述当前发布决定为 `HOLD_MISSING_HUMAN_EVIDENCE`；Phase 2 Release Qualification 因 live 重启窗口仅完成 1/5 轮而记为 **FAILED**；Phase 3–8 均未形成生产资格，v0.2–v0.7 只能标 IMPLEMENTED、不得标 STABLE；Phase 6/7 **真人参与者为 0**，Phase 8 只投递到合成 `TEST_INBOX`。即：工程实现很多，但没有任何一个阶段拿到了「可以给人用」的证据。

**（2）WMA 原件回收损坏，机械检查却报通过——信任链断裂。**
`docs/development/reviews/2026-09-07-project-review-and-next-development-plan.md` 实测复算一个历史运行的三个原件，**3/3 与声明哈希不符**；两份 `.doc` 因 `response.text → write_text()` 被写成损坏二进制（文件头含 `EF BF BD`）；而 `app/services/verifier.py:173–183` 只校验「声明值之间相等、引文非空、文件存在」，不重算本地原件哈希，结果 `verification.json` 仍是 `OK / 42 facts / 0 issues`。这是假通过，直接摧毁了下游所有事实与资格判断的可信基础。

**（3）主线本身有可复现的质量缺陷。**
同一份审查在最新主线隔离副本复现 `mypy --platform linux` **10 个错误**（`artifacts/local_file.py:212–239` 平台分支、`local_human_test/provider_config.py:150–151` WinDLL 类型）；远程 CI 9 项中 2 项（backend-quality、phase4-eligibility）确认失败。

**（4）架构性阻断：审核被设计成无限长的前置链。**
`references/2026-09-13-wma-overall-review-and-overview-replan.md` 第 1.2 节逐条取消了这些前置：方法选择与验证、逐字段核对与事实集晋升、共同条件范围批准与规则批准、多页连续人工批准。原设计下，一份 WMA 返回要进入总览，必须先走完方法认证 → 逐字段核验 → 规则批准 → 发布门；任何一环未完成就整条链停摆。这正是「用户已明确停止、必要时撤销继续补齐所有审核环节的原开发路线」的原因。

**（5）多处接缝断点，使已有模块无法串成产品。**
审查文档 5.3–5.9 列出：`official_evidence.py` 只做请求级保全、不生成 DocumentBlock，而 `extraction.py:354–358` 又拒绝无 Opportunity 的请求级证据包；`compile_legacy_opportunity_rule` 在主代码中无调用方，人工规则批准接不进资格执行；错误否定申诉要求「在排名前三中找到同一匹配」，恰恰把最需要申诉的场景挡在门外；`personal/profile.py:175–187` 自助保存写 `synthetic=False`，而当前身份只有 fixture，却被 `review/service.py` 推导为 `CONSENTED_HUMAN_PARTICIPANT`——存在把测试画像当真人证据的风险。

**（6）身份与授权未产品化。** `personal/auth.py` 与 `review/auth.py` 只允许 development/test 的 fixture 身份，没有邀请、登录/退出、恢复、注销流程。

**（7）过程失控。** 80 个 `codex/*` 分支并存（adjudication、di0、direct-wma、first-visible-result…），同时存在 DI-0 主路线、Native Automation Worker、P10 长分支、8/31 确定性 Excel 路线、9/1 逐片恢复路线、9/7 Direct WMA 路线等多套互斥顺序；README、开发索引、架构图与 P9-B 状态入口互相漂移。

**时间线佐证**：代码提交停在 8 月 26 日，此后到 9 月 15 日的三周只有文档产出（路线图 v1.2、重整设计、9/7 审查、9/13 整体审核规划、9/14 修订）。工作区现有 33 项未提交/未跟踪改动（2 项已跟踪修改、30 项未跟踪、1 项删除）。**这不是"代码写不下去"，而是"方向被判定为走不通后主动停手"。**

### 1.4 遗留代码现状与价值

**可运行性（本次实测）**：`backend/.venv`（Python 3.14.7）完好，`PYTHONPATH=src python -c "from deepaha.main import app"` 成功，应用装配出 **11 条路由**（system / public_opportunities / personal / reminder / feedback / review / local_human_test）；`web/node_modules` 已安装。**旧代码没有烂掉，是可用资产。**

按 `docs/rebuild/03_REUSE_RETIREMENT.md` 的处置分类：

| 类别 | 资产 | 说明 |
|---|---|---|
| 实际复用 | `artifacts/local_file.py`、`object_store.py`；`investigations/wma.py`、`published.py`、`schemas/`；V2 CSS 与图标；sources/opportunities 原身份列 | 内容寻址不可覆盖、WMA 传输、已发布 Agent 绑定、视觉 |
| 保留源码、非默认链 | 原件读器、规则/资格引擎、模型网关、S3 适配、p9b 全套 | 后续可独立接通 |
| 明确退役 | 旧 Provider 与调查 runtime 命令入口、旧 `main.py` 写路由装配、原 Next 业务页/动作、逐字段审核/方法认证/Gold 流程 | 直接运行报退役，不再可执行 |
| 仅保留 | 原迁移与旧数据模型、原配置/启动/CI（置于 `references/`） | 不删表、不回滚、防止旧入口被启动器带回 |

---

## 2. 新项目 D:\DeepAha_Rebuild

### 2.1 定位与基线

- 版本：**3.0.0-rc2**（rc1 = 重建主体；rc2 = 外部信源导入对齐）
- 基线：从资料库 `DeepAha-main.zip` 的隔离副本 `d0918ec1245264e271f42a18d54c0fb903000c00` 开发；远程 main 另观测为 `8f0c4a5d...`，**未下载合并**
- 策略：替换装配入口、保留有效资产；唯一默认入口 `deepaha.main:app` → `product.api.create_app()`
- 定位原文（`docs/rebuild/10_COMPLETION_BOUNDARY.md`）：**可启动的全栈重建候选版**，不是已在服务器上运行的新版，也不是已完成商业化的最终产品

### 2.2 目录结构

| 目录 | 作用 |
|---|---|
| `backend/src/deepaha/product/` | **新增的当前产品模块**，27 个文件约 3,500 行 |
| `backend/src/deepaha/`（其余 22 个模块） | 旧代码全量保留（后端总 62,742 行 > 旧项目 40,772 行） |
| `web/public/product/` | 当前产品前端，原生 ES Modules + V2 视觉（10 文件约 128 KB，其中 brand-v2.css 45 KB） |
| `web/server.mjs` | 可选 Node 同源代理 |
| `scripts/launch_product.py` + 根目录两个 .cmd | 本地启动/停止 |
| `tools/source_asset_importer/` | 随包附带的原来源工具源码（v0.3.1，未删手工功能） |
| `docs/rebuild/`（12 份 + openapi.json + schema-inventory.json） | 重建交付文档 |
| `docs/source-import/`（7 份 + openapi.json） | rc2 信源导入文档 |
| `evidence/` | 34 个实际测试输出/日志 + screenshots + source-import 子目录 |
| `references/` | 旧基线文档副本（legacy-AGENTS/README/CI/compose/main/pyproject/lock）与 2026-09-13 规划原文 |
| `examples/` | 3 个虚构功能样本 ZIP + source-intelligence 样例 |
| `contracts/`、`config/`、`infra/`、`tests/`、`文档/`、`文档2/`、`设计/` | 沿用旧结构 |

> 小瑕疵：根目录存在空目录 `DeepAha_Rebuild/DeepAha_Rebuild/`（解压残留），可安全删除。

### 2.3 已实现功能

**数据层**：19 张表（`product/models.py` 实测）——`product_meta / accounts / sessions / login_attempts / source_profiles / opportunity_identity / result_snapshots / overview_revisions / overview_decisions / overview_publications / tasks / profiles / actions / feedback / notices / audit / import_records`，外加复用旧 `sources`、`opportunities` 身份列。

**API**：53 条路由（本次 grep 实测），分族为 `/api/auth/*`、`/api/catalog/*`、`/api/review/*`、`/api/intake/{source_id}`、`/api/manage/*`（status/connection/sources/tasks/history/legacy）、`/api/me/*`（profile/opportunities/actions/feedback/fit/reminders/notifications/export/data）、`/api/manage/scout/*`；另有 4 条旧路径（`legacy`、`v1/local-human-test`、`v1/review`、`v1/investigations`）显式拦截写方法。

**主链（已接通）**：
`外部研究资产/来源登记 → 人工导入 → 明确 Direct WMA 任务或已有返回 ZIP → 原件保存（内容寻址不可覆盖）→ 可恢复投影 + 局部备注 → 一次整体决定（APPROVE/REJECT）→ 持久总览 → 个人偏好/收藏/行动/反馈 → 站内变化与日期提醒`

**关键行为（文档 `09_VALIDATION.md` 声明 + 本次实测覆盖 76 项）**：原件不可覆盖与读取哈希；压缩包路径/数量/压缩比安全；局部引用缺口仍可收录；核心来源错配阻断；整包与局部排除分开；陌生字段/重复标签/深层对象保留；结构化私密键不公开；精确预览哈希、幂等回执、相反决定并发拒绝覆盖；新版本替换/撤回与旧日期提醒失效；角色隔离、登录限流、会话撤销、CSRF/越权；来源暂停不撤回历史；恢复只回收文件不重发 Prompt。

**运维**：CLI 支持 `backup / verify-backup / restore-backup / identity-adopt / legacy-inventory / legacy-export / upgrade / source-import`；SQLite WAL + 外键 + BEGIN IMMEDIATE；Docker/NGINX/systemd 模板；rc1→rc2 加表升级（先备份校验再加表）。

**安全**：scrypt 密码、随机会话仅存哈希、HttpOnly+SameSite Cookie、写操作 CSRF + Origin 限制、TrustedHost、登录失败限流、**无默认管理员密码**（首次启动要求输入）、公开目录默认关闭、普通注册默认关闭。

### 2.4 本次实测结果（与文档声明的差异）

| 检查项 | 文档声明 | 本次实测（2026-09-17，Windows / Python 3.13.14） |
|---|---|---|
| 后端 `pytest tests/product` | 78 passed | **76 passed, 2 failed**（113.7 秒） |
| 前端 `node scripts/check-product.mjs` | 通过 | **通过** |
| 主应用导入 | — | 可导入（未单独验证启动） |

**两个失败用例（同源，同一根因）**：

1. `test_operations.py::test_backup_restore_into_empty_directory`
2. `test_scout_import.py::test_additive_upgrade_keeps_accounts_and_original_rows`

**根因**：`backend/src/deepaha/product/backup.py:25`

```python
with sqlite3.connect(database_url[...]) as source, sqlite3.connect(copied) as target:
    source.backup(target)
```

`sqlite3.Connection` 的上下文管理器**只管理事务，不关闭连接**。退出 `with` 后 `target` 连接仍持有 `database.sqlite` 的句柄；Windows 不允许删除被占用的文件，于是 `tempfile.TemporaryDirectory()` 清理时报 `[WinError 32] 另一个程序正在使用此文件`，测试失败。Linux 允许 unlink 已打开文件，所以容器里 78 项全通过——**这是典型的 Linux 通过 / Windows 失败，正好落在文档自己标注的 `windows_device: NOT_RUN` 盲区里。**

影响：备份 ZIP 实际已写成功，失败发生在临时目录清理阶段。但真实 Windows 用户执行 `cli backup` 时会残留临时目录，且升级路径（`test_additive_upgrade...`）每次都会触发。

附带观察：测试输出中出现 `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xd2` 线程警告——中文 Windows 下 subprocess 输出为 GBK，被 pytest 按 UTF-8 读取。属于测试环境适配问题，不影响产品代码。

### 2.5 缺失与未验证（严格按交付文档分层）

**代码未接通（明确声明不做，不允许包装成已完成）**：
- 已训练的 AI 排序（现为偏好/关键词/城市相关性）
- 旧可信资格规则消费（新内容资格统一 `UNCERTAIN`，禁止标「符合/不符合」或假百分比）
- 对外通知送达（微信/短信/邮件，仅站内记录 + 日历导出）
- 支付与结算、家长赠送、人格探索、社区、全国全量覆盖

**环境不具备、NOT_RUN（代码路径存在但未实测）**：

| 范围 | 状态 |
|---|---|
| 真实 WMA 调用、成本、文件取回与恢复 | NOT_RUN（无凭据/SDK，2 个 SDK 测试 skip） |
| PostgreSQL 副本迁移、PG 事务并发、Docker 构建 | NOT_RUN（无实例） |
| 原生浏览器 Cookie/CSP/导航、Android/Windows 实机、200% 缩放 | BLOCKED_BY_ADMINISTRATOR / NOT_RUN |
| 原数据库备份、迁移与生产回退 | NOT_RUN（未访问原库） |
| 真实用户价值、资格准确率、AI 匹配质量 | 未验证 |
| 大规模性能、P95、持续运行 | 未压测 |

**验证方式的诚实边界**：13 项浏览器检查、16 次真实 HTTP 是通过「显式测试 HTTP 桥接」完成的——它把界面操作转给真实运行的 API，**没有伪造业务响应**，但替换了浏览器网络传输与导航，因此不能算原生端到端通过。文档明确拒绝把它称为原生验收。

**文档小瑕疵**：`docs/rebuild/04_API_AND_CONTRACT.md` 第 72–79 行存在整段重复（Scout 资产段落重复两次），建议清理。

---

## 3. 新旧差异对比

| 维度 | 旧项目 D:\DeepAha | 新项目 D:\DeepAha_Rebuild |
|---|---|---|
| 核心目标 | 建完整的机会情报生产线与验证体系（P10–P14） | 「拿到结果就能用」的产品闭环 |
| 审核模型 | 方法认证 → 逐字段核验 → 事实晋升 → 规则批准 → 发布（多页、多前置） | **一次整体 APPROVE/REJECT**，局部问题写备注，不阻断其他可用内容 |
| 前端 | Next.js 16 + React 19（41 个 tsx 页面，依赖旧审核路径与 fixture Cookie） | 原生 ES Modules + 真实 API（10 文件），Next 源码保留但不默认运行 |
| 数据库 | PostgreSQL 18（26 个迁移，需 Docker） | **SQLite 实测闭环**，PostgreSQL 为代码支持未实测（47 个迁移文件保留） |
| 身份 | fixture 身份，限 development/test | 真实密码账号（scrypt）+ 会话 + 三角色可组合，无默认密码 |
| 来源获取 | 自建采集平台 + Provider 调查（通用智能体路线） | 外部 Scout 人工导入 + Direct WMA 有界任务；不自建无边界抓取 |
| 数据真相 | 逐字段 VerifiedFact / RuleSet | 原件不可覆盖 + 可重算投影；收录标签独立于 VerifiedFact |
| 资格判断 | 四态资格引擎（但批准接不进执行） | 新内容统一 `UNCERTAIN`，保留保护，不允许假肯定 |
| 交付状态 | `HOLD_MISSING_HUMAN_EVIDENCE`，真人 0 | 可启动候选版，76/78 实测通过，明确列出 8 类 NOT_RUN |
| 诚实度机制 | 阶段门文档与状态漂移、假通过（verifier 报 OK） | 每项能力标注实测/未测，禁止把桥接当原生、把模拟当真实 |
| 代码策略 | 80 分支并行、多条互斥路线 | 单入口、单写主链，旧代码保留但退出默认运行 |

---

## 4. 接续开发必须掌握的背景（按阅读顺序）

1. `README.md` —— 启动方式、能力边界、目录表
2. `AGENTS.md` —— 硬约束（不覆盖用户库、不代签审核、未验证不报 PASS）
3. `docs/rebuild/01_DESIGN.md` —— 权威范围、两个备选为何不采用、数据层与审核职责
4. `docs/rebuild/03_REUSE_RETIREMENT.md` —— 哪些旧代码复用/退役/仅保留
5. `docs/rebuild/09_VALIDATION.md` —— 已验证什么、没验证什么、复现命令
6. `docs/rebuild/10_COMPLETION_BOUNDARY.md` —— **三层不可扩大解释表**，接续第一原则
7. `docs/rebuild/07_MIGRATION_RECOVERY.md` —— 旧库迁移顺序与受控 `identity-adopt`
8. `docs/rebuild/04_API_AND_CONTRACT.md` + `openapi.json` —— 接口与 WMA 输入契约（注意旧前端不能只改前缀调用）
9. `docs/source-import/05_VALIDATION_AND_BOUNDARIES.md`、`06_CODEX_HANDOFF.md` —— rc2 范围与接续验收核心
10. `references/2026-09-13-wma-overall-review-and-overview-replan.md` —— **旧路线被废止的原始依据**，理解「为什么这么改」
11. `evidence/31_final_test_run.txt`、`28_final_browser_bridge.txt`、`29_native_browser_attempt.txt` —— 原始验证输出
12. `backend/src/deepaha/product/models.py`、`api.py` —— 现代表结构与实际路由

**不可违背的约束（来自 AGENTS.md 与各设计文档）**：
- 不改用户库、不清表、不推送/合并/部署（除非明确授权）
- 未验证的 SDK / 数据库 / 浏览器 / 真实用户不能报 PASS
- 先写失败用例，再实现，再定向验证；单个任务窗口
- 外部 Scout 人工导入，不自建无边界抓取智能体
- 真实材料出现新结构时，优先小范围适配到内容投影；**不得恢复逐字段方法认证作为前置**
- 接通旧可信规则引擎时，不得为了产生肯定判断而删除 `UNCERTAIN` 保护

---

## 5. 待解决问题清单

| # | 问题 | 性质 | 优先级 |
|---|---|---|---|
| 1 | `backup.py` SQLite 连接未关闭，Windows 下 2 个测试失败、临时目录残留 | **本次实测发现的真实缺陷** | P0 |
| 2 | 中文 Windows 下 subprocess 输出 GBK 导致测试线程 UnicodeDecodeError 警告 | 测试环境适配 | P1 |
| 3 | 真实 WMA 三文件从未跑通，无凭据/SDK；2 个测试因此 skip | 阻塞核心业务验证 | P0 |
| 4 | PostgreSQL 从未实测；PG 并发/迁移/往返全是代码假设 | 阻塞生产部署 | P0 |
| 5 | 原生浏览器被管理员策略阻断，现有 13 项检查走 HTTP 桥接 | 阻塞前端验收 | P1 |
| 6 | Windows 实机（双击启动、DPAPI 密钥、200% 缩放）未验 | 阻塞交付给非技术用户 | P1 |
| 7 | 原数据库未备份、未迁移，`identity-adopt` 未在真实库跑过 | 阻塞数据连续性 | P1 |
| 8 | 远程 main `8f0c4a5` 未集成；本机未提交更改不在包内 | 版本对齐风险 | P1 |
| 9 | 通知只有站内 + 日历，无微信/短信/邮件送达 | 功能缺口（有意延后） | P2 |
| 10 | 排序为偏好关键词，非训练模型；资格统一 UNCERTAIN | 功能缺口（有意延后） | P2 |
| 11 | 复杂更正作用域、官方撤销文本自动理解未接通 | 已知限制 | P2 |
| 12 | 文档重复段落（04 号）、根目录空嵌套目录 | 卫生问题 | P2 |

---

## 6. 建议的下一步工作清单

### P0：先把「能跑」变成「在 Windows 上也真的能跑」

**P0-1 修复备份连接泄漏**（预计 5 行改动）
- 位置：`backend/src/deepaha/product/backup.py:25`
- 做法：改用 `contextlib.closing(sqlite3.connect(copied))`，或在 `with` 块内显式 `target.close()`；`source` 同理
- 验收：Windows 下 `pytest tests/product -o addopts= -q` 由 76 passed / 2 failed 变为 **78 passed / 0 failed**；并实际跑一次 `cli backup → verify-backup → restore-backup` 确认临时目录无残留

**P0-2 补齐真实 WMA 链路**
- 取得真实凭据与已发布 Agent，用一份真实三文件包完成一次「导入 → 整体通过 → 总览回读」
- 验收：保留实际 Agent 发布版本、材料清单与缺口记录；**没有凭据时停在任务契约验证，禁止伪造成功**

**P0-3 PostgreSQL 隔离副本验证**
- 在 PG 副本上重跑决定/并发/撤回/权限测试，验证 advisory lock 串行化与迁移往返
- 验收：与 SQLite 同套用例通过，并给出迁移 head 对照结论；不据此宣称原库已迁移

### P1：补齐真实环境证据

**P1-1 原生浏览器验收**：在有正常浏览器权限的隔离环境跑 `tests/e2e/native_browser_check.py`（需 `E2E_ALLOW_WRITES=1`、loopback、测试账号、虚构样例；**不要对真人库跑**），验证 Cookie / CSP / 导航 / 下载

**P1-2 Windows 实机**：双击 `启动机会星图.cmd` 全流程（含首次安装依赖、输入首个账号、DPAPI 密钥保存、200% 缩放布局）

**P1-3 原库只读清点**：先备份原库与原件 → 只读 inventory → 副本上试 `identity-adopt` → 确认映射后再导入返回；未确认关联不得宣称自动连续

**P1-4 版本对齐**：核对当前包 `d0918ec` 与远程 main `8f0c4a5`、以及本机 33 项未提交改动，写清差异后再决定合并策略；不得用 ZIP 直接覆盖已部署目录

### P2：功能扩展（必须在 P0/P1 之后，且不得改变既有使用方式）

- 对外通知渠道（先选定一种：微信模板或邮件），含退订、频控、失败处理与送达证据
- 旧可信规则引擎消费：只能消费当前有效且范围完整的依据，保留 UNCERTAIN 保护
- 复杂更正作用域与官方撤销文本理解
- 文档卫生：清理 04 号重复段落、删除空嵌套目录

### 明确不要做的事

- 不要恢复逐字段方法认证 / Gold 流程作为收录前置（这是旧项目失败的根因）
- 不要为了「看起来完整」把未接通模块包装成已完成
- 不要新建第二条写主链或第二套来源/机会身份库
- 不要对原项目全量跑可能连接真人库的 integration 测试
- 不要在没有凭据时把 SDK 跳过项改成假通过

---

## 7. 复现命令

```bash
# 后端产品测试（Windows 实测：76 passed / 2 failed，修复 P0-1 后应为 78 passed）
cd D:\DeepAha_Rebuild\backend
PYTHONPATH=src python -m pytest tests/product -o addopts= -q

# 前端检查（实测通过）
cd D:\DeepAha_Rebuild\web
node scripts/check-product.mjs

# 真实研究文件回放（自行提供文件，永远在临时库运行）
python tests/e2e/source_import_real_archive.py /path/to/WB-scout.zip --output /path/to/replay.json
```

> 本机已备好隔离环境：`C:\Users\LENOVO\.workbuddy\binaries\python\envs\deepaha_rb`（Python 3.13.14 + fastapi 0.128.2 + sqlalchemy 2.0.50 + psycopg 3.3.5），可直接用于上述命令，不污染系统 Python。

---

## 8. P0 执行结果（2026-09-17 16:40 更新）

### P0-1 备份连接泄漏 —— 已完成

修改：`backend/src/deepaha/product/backup.py`

- 第 25 行：`sqlite3.connect` 改为显式 `close()`/`closing()`，修复 Windows `[WinError 32]`
- 第 84 行：恢复路径改为 `c = sqlite3.connect(...)` + `with c:`（保留事务提交）+ `finally: c.close()`；**不能只用 `closing`，否则会话撤销的 UPDATE 不会提交**
- 新增两处注释说明原因，避免后人改回

验证：

| 项目 | 结果 |
|---|---|
| `pytest tests/product`（SQLite / Windows） | **78 passed, 0 failed**（修复前 76/2） |
| 实机 `cli backup → verify-backup → restore-backup` | 全部成功；`sessions_revoked: true`（证明事务提交未被破坏） |
| 临时目录残留 | before 6387 → after 6387，**零残留** |

### P0-3 PostgreSQL —— 已完成（隔离实例真实验证）

环境：Docker Desktop 29.6.1 + `postgres:18`（实际 18.6），容器 `deepaha-pg-verify`，宿主机端口 **55433**（不占用项目熟悉的 55439/8000/8011）。

**重要方法学发现（写下来避免重复踩坑）**：
`tests/product` 单元测试**不读 `DEEPAHA_DATABASE_URL`**，它们自建临时 SQLite 库。所以「在 PG 环境下跑 pytest 得到 78 passed」**不能作为 PG 验证证据**——本次先跑了一次，随后核对 PG 内 `\dt` 为空，确认该结论无效并改用应用路径验证。

正确的 PG 验证路径（本次实际执行）：

```bash
export DEEPAHA_DATA_DIR=<隔离目录>
export DEEPAHA_DATABASE_URL=postgresql+psycopg://deepaha:...@127.0.0.1:55433/deepaha
python -m deepaha.product.cli init            # 建表
python -m deepaha.product.cli user-add ...    # 建账号（--password-env）
python -m deepaha.product.cli serve --port 8098
# 登录 → 登记来源 → 导入样本 ZIP → 整体 APPROVE → 回读 catalog
```

结果：

| 检查 | 结果 |
|---|---|
| `cli init` | 成功，PG 内建出 **26 张表**（product_* + sources/opportunities） |
| 完整业务闭环（登录→来源→导入→审核通过→总览回读） | **通过**，返回 `public_ids`、`saved_at` |
| 数据落库核对 | accounts 1 / sources 1 / snapshots 1 / revisions 1 / decisions 1 / publications 1 / audit 5 |
| 是否误用 SQLite | 数据目录内**无 `.db` 文件**，仅有 objects/ |

结论：`postgresql` 由 **NOT_RUN → PASS（隔离 PG 18.6 实例，应用路径完整闭环）**。仍**不等于**原 PostgreSQL 库已迁移——旧库迁移（P1-3）依然未做。

### 顺带完成

- Windows 实机（P1-2 部分）：隔离目录 `init → user-add → serve → 登录 → 登记来源 → 导入 → 整体通过 → 总览回读` 全链走通；含 CSRF、HttpOnly 会话、角色检查
- 文档：`docs/rebuild/04_API_AND_CONTRACT.md` 重复段落已清理
- 目录：根级空嵌套目录 `DeepAha_Rebuild/DeepAha_Rebuild/` 已删除

### 仍阻塞（需要你提供条件）

| 项 | 缺什么 |
|---|---|
| P0-2 真实 WMA | **SDK 已装好，只差 API Key + Agent ID**（见下节）。来源政策已就绪 |
| P1-1 原生浏览器 | 浏览器访问本机地址被管理员策略阻断（`ERR_BLOCKED_BY_ADMINISTRATOR`），脚本与环境已备好，需在有权限环境跑 |
| P1-3 原库迁移 | 未备份、未访问原库，需你确认原库位置并先做备份 |
| P1-4 版本对齐 | 远程 main `8f0c4a5` 未下载；本机 33 项未提交改动不在包内 |

---

## 9. WMA 代码核查：不是缺失，是从未合流（2026-09-17 补充）

核查结论：**WMA 是旧项目里最成熟的一块，新项目几乎原样继承；问题从来不是"没写"，而是"没合进 main"。**

### 9.1 代码确实存在且成熟

| 证据 | 结果 |
|---|---|
| 新项目 `investigations/` 模块 | **51 个文件、12,226 行**，含 `wma.py`(408)、`store.py`(717)、`models.py`(31.9KB)、`runner.py`、`dispatch.py`、`published.py`、`prompt.py`、`schemas/` |
| `wma.py` 与旧分支逐行对比 | 旧 405 行 → 新 408 行，**唯一差异是把 `import httpx2` 改成 httpx 兼容别名**。即：原样继承，仅做 HTTP 库适配 |
| `DirectWmaClient` 能力 | `inspect_release` / `create` / `resume` / `upload` / `prompt` / `download` / `aclose`；发布绑定校验、数据面文件读写、错误码体系 |
| 产品层 `product/worker.py`(184 行) | 任务领取 → 会话 checkpoint（先落 runtime_id/session_id 再请求）→ 上传 schema 与 task.json → prompt → 回收三文件+附件 → 打包 → ingest；**恢复模式只回收文件、不重发 Prompt**；政策版本冻结校验、预算、心跳、取消、审计、周期调度绑定授权人 |

### 9.2 但它从未进入旧项目 main

| 检查 | 结果 |
|---|---|
| 旧项目 `main` 里的 `investigations/` 文件数 | **0** |
| 旧项目 `main` 里 wma 相关文件 | **0** |
| Direct WMA 实际所在 | 分支 `codex/delivery1-direct-wma`，最后提交 `7e6d9e1`（2026-09-08），**未合入 main** |
| 旧项目 main 里的替代物 | `local_human_test/`（旧 Provider 调查路线，已被判定退役） |

即：旧项目有 80 个分支，WMA 成果散落在 `codex/delivery1-direct-wma`、`codex/announcement-*`、`codex/cross-level-*`、`codex/group-*` 等分支上，**没有一条回到 main**。新项目的实际贡献是把这些成果裁剪合流：

- 旧 `delivery1-direct-wma` 分支：87 个 investigations 文件 → 新项目保留 **52 个**
- 两边共有（原样沿用）16 个：`wma.py`、`runner.py`、`store.py`、`published.py`、`prompt.py`、`bindings.py`、`delivery.py`、`documents.py`、`facts.py`、`models.py`、`registration.py`、`rules.py`、`field_mapping.py`、`contracts.py`、`rule_contracts.py`、`cli.py`
- 新项目独有 35 个：`announcement_*`、`cross_level_*`、`group_*`、`applicability.py`、`dispatch.py`、`document_exclusions.py`、`evidence_checks.py`、`relation_*` 等——来自旧项目其他未合并分支
- 被裁掉的：`evidence_blocks.py`、`full_scope.py`、`material_reviews.py`、`qualification.py`、`replay_views.py` 等——属于已废弃的逐字段审核路线

### 9.3 SDK 已解决，只剩凭据

`requirements-wma.txt` 里的包名是 **`codebuddy-cloud-agent-sdk==0.3.4`**（代码里 import 的是 `cloud_agent_sdk`，二者不同名，这是之前误判"SDK 不存在"的原因）。

本次已安装到隔离环境，`cloud_agent_sdk` 可导入。安全验证（用假凭据、不发起任何远程调用）：

```
DirectWmaClient 构造成功 → SDK 已绑定，未报 WMA_SDK_UNAVAILABLE
binding_evidence() → WMA_SESSION_NOT_VERIFIED（未建会话时正确拒绝，保护逻辑生效）
```

安装 SDK 后重跑 `pytest tests/product`：**78 passed，无回归**。

> 诚实边界：SDK 装上 ≠ 真实调用已验证。现有 WMA 测试是契约/假件级，**没有一次真实腾讯调用**。真实验证仍需你提供 API Key 与 Agent ID，且要用 `config/sources/direct-wma-local.json` 里已批准的两条端点（zjhr、rlsbt）小范围跑一次。

---

## 10. 真实 WMA 验证结果（2026-09-17 17:20，凭据已提供）

凭据经 `文档2/企业版Work buddy  Code body  AIP.txt` 提供，全程只在子进程环境变量中使用，**未写入任何文件、日志、代码或文档**。

### 10.1 真实连接：通过（真实控制面调用）

`POST /api/manage/check-connection` 返回 `connected: true`：

| 项 | 实测值 |
|---|---|
| agent_id | `<YOUR_WMA_AGENT_ID>` |
| release_version | **v5** |
| published_model | **deepseek-v4-pro** |
| 已挂载技能 | browser-use、markitdown-skill、pdf-image-text-extractor、playwright-browser-automation、tencentcloud-ocr、tencentcloud-ocr-recognizetableaccurate |
| sdk_available | true |

这是**真实的腾讯控制面调用**，不是假件。

### 10.2 在线调查：会话已建立，但预算内未完成

用已批准的 zjhr 栏目页发起一次真实调查（`INVESTIGATE`，预算 600 秒）：

| 阶段 | 实测 |
|---|---|
| 远程会话创建 | **成功**，取得真实 `runtime_id` / `session_id` |
| Prompt 发送 | 成功，stage 到达 `PROMPT_STARTED` |
| 结果回收 | **超时** → `WMA_TIMEOUT` → `NEEDS_RECOVERY` |
| 触发恢复（只回收、不重发 Prompt） | `WMA_ARTIFACT_NOT_FOUND`——Agent 在超时前未写出结果文件 |

任务详情接口不返回 `workspace`（数据库里实际有值 `/workspace/deepaha/<task_id>`），属接口显示问题，不是数据缺陷。

**这不是代码缺陷**：系统行为完全符合设计——不伪造成功、进入可恢复状态、审计完整记录（含"仅回收已有文件与整理；不会再次发送调查提示词"）。

### 10.3 真实历史返回包：收录闭环通过（零成本、真实数据）

来源：`D:/Agent/wb-agent-cli/deepaha-agent-poc/runs/`（慧行指出项目里有历史返回，属实）

| 批次 | 附件 | 结果 |
|---|---|---|
| `zjhr-live#1`（2026-09-03，seed=https://www.zjhr.com/） | 7 个，**声明 vs 实际哈希全部 MATCH** | 导入 → 62 字段 → 9 项引用未定位（备注保留）→ 整体通过 → 总览可读 |
| `wma-zjhr#4`（2026-09-04） | 3 个，**声明 vs 实际哈希 3/3 MISMATCH** | 见下 |

### 10.4 决定性对照：新系统没有重演"假通过"

这是本次最有价值的一项。`wma-zjhr#4` 正是 2026-09-07 审查实测的那批损坏原件（当时旧项目 `verifier.py` 只比对声明值，输出 `OK / 42 facts / 0 issues`）。

新系统导入同一批文件的表现：

```
status      = PENDING
can_approve = False
blockers    = ['未找到可安全呈现的机会对象。']
附件报告：
  公告正文 -> integrity = MISMATCH | state = 已保存
  附件1    -> integrity = MISMATCH | state = 已保存
  附件2    -> integrity = MISMATCH | state = 已保存
notes:
  - 材料“…”的文件校验不一致，相关引用不用于计算。（×3）
  - “…”的主要来源无法归属到本次允许的机构，未纳入收录范围。
```

**旧项目：报 OK / 0 issues，放行。**
**新项目：重算实际字节哈希 → 报 MISMATCH → 相关引用不用于计算 → 阻断收录。**

旧项目失败根因之一（假通过）已被实证修复。

### 10.5 P0-2 状态更新（严格分层，不夸大）

| 能力 | 状态 |
|---|---|
| WMA 凭据有效性与已发布 Agent 连接 | **PASS**（真实控制面调用） |
| 真实会话创建与 Prompt 派发 | **真实发生**（取得 runtime/session），但本次未完成 |
| 在线调查 → 回收产物 → 收录（端到端） | **NOT_COMPLETE**：600 秒预算内超时，恢复无产物 |
| 真实历史返回格式 → 解析 → 收录 → 总览 | **PASS**（真实数据，7 附件哈希全匹配） |
| 损坏原件是否被诚实识别 | **PASS**（MISMATCH + 阻断，未假通过） |

下次若要完成端到端在线调查：把预算提到上限 1800 秒，或改用**单条具体公告 URL**（栏目页范围过大是超时主因）。

### 10.6 凭据文件的处置（已完成）

**更正一处此前的误判**：`D:\DeepAha_Rebuild` **当前不是 git 仓库**（无 `.git`），所以此前"已被 git 跟踪"的判断不成立——那次 `git check-ignore` 是因为找不到仓库而报错，被误读成了有风险。当前并无泄露路径。

不过规则仍然加上了（预防日后 `git init` 或整个目录被拷入仓库）。已在 `.gitignore` 末尾追加：

```gitignore
# 凭据与密钥：任何位置、任何命名都不得进入版本库
*AIP.txt
*AIP*.txt
*API-Key*
*API-KEY*
LLM-API*.txt
*密钥*
*凭据*
*.credential
*.credential-key
secrets/
*.pem
*.key
```

**已实测验证**（在临时目录 `git init` 后按同样布局造文件，未污染项目）：

| 文件 | 是否被忽略 |
|---|---|
| `文档2/企业版Work buddy  Code body  AIP.txt` | **忽略 ✔** |
| `文档2/LLM-API.txt` | **忽略 ✔** |
| `config/my.credential` | **忽略 ✔** |
| `文档2/正常文档.md` | 保留（正常文件不应被误伤）✔ |
| `backup/dump.zip` | 保留（备份不是密钥）✔ |

`git status -uall` 中已确认凭据文件不再出现。

所有服务进程已停止，凭据仅存在于你原来那个文件里，未复制、未写入其他位置。
