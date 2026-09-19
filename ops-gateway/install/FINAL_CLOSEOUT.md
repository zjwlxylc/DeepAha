# DeepAha Ops Gateway v1 — 一次性完工执行单

## 任务与执行授权

本文件由用户已提供的 `SG8A_PRODUCT_GIT_BASELINE_PLAN`、`TRUE_STAGING_ISOLATION_PLAN` 合并而成。用户把本文件交给 Codex 执行，即授权在下述范围内连续实施，不再逐阶段索要方案确认。之前“只设计”“不安装隔离环境”“staging 切换另行确认”的限制，在本文件明确授权的范围内被替代；生产业务及数据保护限制继续有效。

目标：当前线上业务不被替换；SG8-A 有正式 Git 来源；有可安全测试的独立 staging；Gateway 能执行受控的同 schema 发布、备份、重启和回退；准备可被 ChatGPT 实际调用的认证入口。不是再次交付两个 PENDING 方案。

执行方式：单任务、Locked Internal Batch。利用当前会话的实查证据与两份方案，内部按依赖顺序开发、测试、安装、自审，连续推进。普通配置选择和可自行解决的环境问题不交给用户反复决策。单个失败点最多三次有依据的修复尝试；仍有真实阻塞则关闭受影响能力，继续不依赖它的安全工作，最终一次性汇总。涉及生产数据风险或意外线上故障须及时告知，不能为了减少沟通隐瞒。

## 已固定的决策

- Product 仓库拟定为 `zjwlxylc/DeepAha-Product`，private。已获准创建；先检查同名仓库，只有确认属于同一代码线才复用，不覆盖其他内容，不更改既有仓库可见性。
- Gateway 代码继续在 `zjwlxylc/DeepAha` 的 `ops-gateway/` 独立目录维护。已安装起点为 `1d3f524b5d2d78a9b1615f852faef9fe4c78eba0`；本文件不是新安装版本，不要求回退到该 SHA。
- Product 起点为冻结的 `DeepAha_Rebuild_3.8.0-rc1_SG8_A.zip`，SHA256 `45a4d2078cb585c534b5327f86f24dc2a6c4469dde7f6312ca4e1e02b0faddbe`；基线 tag 为 `product/3.8.0-rc1-sg8a`，不得覆盖同名 tag。
- 环境按实际用途映射：承载 www 的现有 SG8-A 系统一律视为 `production`，即使 unit、目录、账号和数据库名称含 staging。`staging` 只指新隔离环境。精确资源绑定由当前已核实 S0 证据填入 root-owned 配置；不能由调用者传入路径、数据库、服务名或 URL。
- 本次授权建立隔离环境，并在隔离验证通过后仅切换 `staging.deepaha.com` 到新 upstream；www 的 upstream、业务 release、current、数据库和原件保持原样。
- v1 的数据库策略为 `SCHEMA_POLICY=NO_SCHEMA_CHANGE`。当前 Product 实库没有 `alembic_version`；包内代码 head `20260912_0055` 不是实库 revision。保留 `UNTRACKED / NO_ALEMBIC_VERSION_TABLE`，绝不 stamp、upgrade/downgrade 这条未证明适用的链。
- Product 数据库代际记录为 `deepaha-product-v1-actionable2-actionloop1-lab2`。这只是已有契约值，须只读核对实际 meta/schema，不能改库让它匹配。新增数据库代际迁移不属于本次必做前置。
- 不升级或重启共享 PostgreSQL；不为消除历史命名而迁移/重命名生产库；不用空的 deepaha_prod 替换现有业务库；不导入真实用户副本到测试环境。

## 连续实施：三个内部工作包，不设人工接力门

### A. 固化 Product 来源，并搭好真正独立的 staging

1. 在新的本地目录校验并解包冻结 ZIP，不在服务器 release 原地 git init。建立无父基线提交和上述 tag。保留来源清单、纳入文件 SHA256 清单及排除清单；禁止伪称筛选后的 Git 树是 ZIP 全量逐字副本。排除凭据、env、数据库、真实原件、运行数据、venv、缓存、部署工作目录及交付 ZIP；测试必需的嵌套无敏感 ZIP 须逐项检查，不能因一刀切排除而破坏测试。完整秘密扫描须在首次 push 前执行。
2. 依赖锁定、安全修正和部署适配另作后续提交，不混入“原包基线”。读取真实 Product 模块、启动脚本及 schema/meta 检查；保留旧 Alembic 文件的历史来源，但明确禁止在 Product 实库使用，不能把它们自动接成新 Product 迁移链。
3. 推送 private Product 仓库；只读验证当前生产代码与纳入基线文件的对应关系，记录真实生成的 SHA、数据库代际、schema 指纹及排除范围。版本映射置于独立 root-owned 运维元数据，不编辑线上源码或现有 current。GitHub 连接器访问这个新私有仓库如需账户授权，最后集中列出，不擅自把仓库改公开。
4. 实施已拟定的 staging-isolated 拓扑：独立 OS 用户、unit、env、release/current、数据及 objects、备份目录、数据库及最小权限账号；优先使用已计划的 loopback 8200，冲突时内部选空闲端口并同步全部配置。不要复用生产可写目录、cookie Domain、session secret、队列或供应商密钥。WMA、外发通知和真实调度关闭，只使用 synthetic/fixture 数据。
5. 隔离库只允许在确认空的新库内，使用经源码核查的 Product 专用初始化路径。不能调用包内旧 Alembic 链。若不存在安全的 Product 空库初始化入口，补最小、仅新空库可运行的 bootstrap 并测试；不要碰现有真实数据库。新库的 schema/meta 须与当前 Product 契约相容，而非伪造 revision。
6. 执行 Product 回归、已有 Gold Oracle、前端契约、typed-copy 与部署契约、HTTP Smoke。验证双向数据库访问拒绝、生产 env/原件对 staging 用户不可读、进程实际连接隔离库；必要的共享访问配置改动仅针对新增账号/数据库，备份、校验并 reload，不扩大生产账号权限或重启数据库。限制构建/测试 CPU、内存、I/O，持续观察 www 健康。
7. 通过后备份并仅切换 staging vhost 到新服务，nginx -t 成功才 reload；保留原访问控制，设置明确的测试环境标识。核对 www 配置/业务 PID/current/数据库连接未被本任务改变。失败只回退本轮 staging 路由与新增资源，禁止恢复生产数据库来补救。

### B. 把 Gateway 从“只读外壳”接成可用的受控发布入口

主要改动范围：`ops-gateway/src/deepaha_ops/{main,auth,config,store,runner,audit}.py`、静态 OpenAPI、对应测试和安装文档；服务器 adapter 的实机映射保留在私有位置。只做本任务必需修正，不重构业务系统、不建设通用运维平台。

1. 增加动作×环境权限。所有业务 status/logs/restart/backup/deploy/rollback 明确环境；缺少环境的变更请求拒绝，不能默认 production。gateway 自身日志单独处理。staging token 不能读到 production 操作详情或触发任何生产变更；只读 token 不能写。不能只把现有总开关改 true 就结束。
2. API/工具层和 root-owned adapter 均校验固定动作、环境及允许参数。使用最小 sudo 权限，Gateway 非 root，安装代码与 adapter 对运行用户不可写；禁止任意 Shell、SQL、路径和 unit。构建、依赖脚本、Product 启动及测试代码不能以 root 执行。仅执行受信私有仓库中已通过测试/审核的完整 SHA；任意 SHA 格式正确不等于获准发布。
3. 为每个可部署版本生成受信发布清单，绑定仓库、完整 SHA、构建产物哈希、Product 代际、schema 指纹、测试结果、兼容回退范围和健康检查。校验当前版本/目标版本，阻止旧请求覆盖较新发布。不能仅信任调用者传来的 schema_change_in_release=false；用源码差异及隔离库结构比较验证无 schema 变化，并检查启动路径不会隐式升级实库。发现变化即拒绝，报专用迁移需求，不在本次硬接旧 Alembic。
4. 同一环境所有变更走同一宿主锁，包括 Codex 直接使用官方部署脚本的路径。任务异步、返回 operation id，内部限时并限制队列、并发和输出；流式有界读取，不能先无限收集再截断。幂等绑定认证主体、动作、环境和载荷，同键异载荷拒绝；重试不可重复操作。进程重启后遗留 RUNNING 记为结果未知，先核对，不伪称 ABORTED 已撤销，不自动重新执行。
5. 审计写入失败时不得继续变更。审计应验证已有链，损坏不能静默重置；日志输出脱敏，并明确本地 hash chain 不是防 root 篡改的证明。不向模型返回原始数据库、凭据文件或无界日志。
6. 实现同 schema deploy/rollback、固定服务 restart、备份及完整性核验。备份范围、账号/原件一致性和必要暂停窗口按 Product 原生能力如实说明。rollback 只允许有效且兼容的历史版本；只有一个 baseline 时不能假造 previous，更不能回到旧原型。失败发布的应用恢复不得冒充数据库恢复。
7. 在新 staging 中通过 Gateway 实际完成部署→检查→重试同幂等键→备份→恢复到另外隔离演练库→回退。为证明回退可用，可创建只含发布版本标识的合成验证提交，不改变业务行为/schema，不把它列为 production 候选。加入鉴权/跨环境/参数/并发/中断/审计失败反例；成功证据不能用 dry-run 顶替。
8. 验证通过后启用 staging 白名单变更；保留全局紧急关闭能力。production 的代码发布和回退接口可准备完成，但本轮不执行生产部署、业务重启、备份暂停或迁移。生产变更采用按次人工授权：绑定动作、环境、精确版本及当前状态、有过期时间、只能使用一次，授权权力不能授予模型委托凭据；复用成熟确认机制，不能把模型自己填固定 confirmation 字符串当作人工批准。生产拒绝门/预演可验证，但不得标为生产成功变更已验证。Beta 用户创建等可选能力保持禁用，不作为本轮完工依赖。

### C. 完成 ChatGPT 接入所需的协议、认证和交付

目标是工具可调用，不是仅让浏览器能打开 ops 域名。不要把静态 openapi.yaml、curl 成功或本机 Codex MCP 成功冒充当前 ChatGPT 会话已连接。

1. 优先完成远程 MCP 的最小封装，路径采用 `/mcp`，使用标准 SDK 和 Streamable HTTP。仅暴露已授权运维工具和 operation 查询，准确标记读写/破坏性，不开放任意执行；所有入口复用同一鉴权、环境限制、审计及生产授权门。
2. ChatGPT MCP 的认证按当前官方支持的 OAuth 2.1 路径实现，不假定网页 MCP 可以像本地 Codex 一样配置任意 Bearer API Key。优先复用已配置成熟身份提供方；没有时采用成熟可自托管组件的独立、单管理员配置，关闭公开注册，不连接或修改 Product 用户库，不手写密码学/授权协议。不得为了接通新增收费服务或关闭认证。落实 discovery、PKCE S256、redirect 校验、resource/audience/scope、token 过期/刷新/撤销，复用标准 SDK 与组件并做负例测试。
3. 不再让用户选择秘密文件目录：复用已安装的安全存储；新增本机凭据默认保存在 Windows Credential Manager 的 DeepAha/Ops 命名空间，服务器必要凭据进入独立受限 secret 文件并记录拥有者/模式。API 校验器只保存 Bearer 哈希；签名私钥、身份提供方凭据等不能冒充只存哈希。文档和聊天仅报告凭据名称/存储位置，绝不回显秘密、URL token 或一次性代码。实际账户登录/同意由用户本人完成，不替用户登录账户。
4. 同步修复已有 OpenAPI 作为可选的私有 GPT Actions 接入材料：API Key 由编辑器安全配置；幂等键放在严格校验的请求体内并与 REST/MCP 共用核心逻辑，不能依赖 Actions 不支持的自定义 Idempotency-Key 请求头。生产操作标记 x-openai-isConsequential=true；请求快速返回任务 ID，长任务查询结果。Actions 是另一个私有 GPT 入口，不能宣称它自动接入当前项目对话。
5. 默认走 MCP；只有实际账户/工作区不支持目标写工具时，才报告这个平台限制并提供上述 Actions 备用材料，不同时要求用户部署两套系统、不伪装 read-only 工具执行写操作、不降低鉴权来绕过限制。官方文档变化以实施时核对为准，不能凭过往套餐记忆断言能用。
6. 在有权限的执行环境跑真实 MCP 握手、tools/list、已认证只读调用和 staging 操作测试。把全部用户账户侧必需动作合为一份短说明：准确入口/字段、认证方式、新 Product 私有仓库的访问授权（如需）、一条安全验证口令。未获用户账户授权前只记 SERVER_READY / CLIENT_AUTH_REQUIRED；必须看到 ChatGPT 实际工具调用的匹配 request/operation 回执后才记 CHATGPT_CONNECTED。

## 验收、停损与输出

开发采用 RED→GREEN，修复必要反例；相关测试通过后提交，保留可回查 SHA。既有 main 不 force/reset；候选审查、测试通过才可按仓库已授权方式合并，禁止为满足 ff-only 强推主线或绕过保护。部署使用已验证不可变提交，不从未提交工作树构建。若仓库策略不允许当前身份完成合并，保留候选并集中报告，不冒充合并。

对旧只读 Gateway 做可恢复更新，保留回退包；不重装已经通过的 TLS/服务基础设施。实机拓扑、私有 repo 信息与运维证据放私有位置，不把敏感报告 push 到公开 Gateway 仓库。只提交必要的通用代码、合成测试和无秘密说明。

允许自动推进：基线登记、新隔离环境建立、staging 路由切换、Gateway 修正/安装、隔离环境实测、通过后启用 staging 变更、生产按次授权门及接入材料。禁止顺手执行：www 版本切换、生产数据库变更/恢复/重命名、生产业务停启、开放 WMA/外发、为测试使用真实个人数据、主机/共享数据库大版本升级。

遇到秘密泄露、来源不一致、越权或意外生产影响：立即停止受影响动作并封闭权限，仅撤销本轮已明确可逆变更。权限/登录/套餐或资源不足等不能自行解决的事项，最终一次性列出最小人工动作；不能承诺它们不存在。完成不依赖这些阻塞的安全工作，不用另起方案评审拖延。

最后只给一次交付报告及一个无秘密连接包。报告逐项用实际证据填写，不预填 PASS：

- PRODUCT_GIT_BASELINE、PRODUCT_REPO、BASELINE_SHA、TAG、PACKAGE_PROVENANCE
- PRODUCT_DATABASE_GENERATION、DATABASE_REVISION=UNTRACKED（除非有新实证）、SCHEMA_POLICY=NO_SCHEMA_CHANGE
- STAGING_ISOLATION、STAGING_DOMAIN、STAGING_MUTATIONS、STAGING_DEPLOY_BACKUP_ROLLBACK_EVIDENCE
- PRODUCTION_UNCHANGED、PRODUCTION_MUTATIONS=PER_OPERATION_HUMAN_AUTH_REQUIRED、PRODUCTION_MUTATION_LIVE_TEST=NOT_RUN
- GATEWAY_SHA、ADAPTER_SHA256、MCP_SERVER、AUTH_PROTOCOL_TESTS
- CHATGPT_CONNECTION=CONNECTED / CLIENT_AUTH_REQUIRED / PLATFORM_BLOCKED（按事实）
- 凭据安全存储位置（不含值）、尚需本人操作的唯一汇总清单（如无则写 NONE）

成功收口的含义：服务器端所需代码与隔离实测在本任务内完成；不存在可自行完成却遗留的“待写方案/待造 adapter”。用户账户授权和首次真实 production 操作是独立事实，不能谎称已完成。

## 实施时参考的官方资料

- MCP 认证：https://developers.openai.com/plugins/build/auth
- ChatGPT MCP 配置与账户权限：https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- GPT Actions 认证：https://developers.openai.com/api/docs/actions/authentication
- GPT Actions 限制与确认标记：https://developers.openai.com/api/docs/actions/production

这些外部资料用于接入协议，不覆盖用户提供的当前 SG8-A 实机事实。本文是执行约定，不是任何服务器动作已完成的证明。
