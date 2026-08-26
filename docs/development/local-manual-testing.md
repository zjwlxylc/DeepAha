# DeepAha Windows 本地人工体验

## 开始与停止

1. 双击仓库根目录的 `启动 DeepAha 本地人工测试.cmd`。
2. 等待窗口完成依赖、持久化 PostgreSQL、Migration、审核身份、API、Worker、Web 和浏览器检查。
3. 浏览器会打开 `/review/human-test` 本地人工体验控制台。
4. 使用结束后双击 `停止 DeepAha 本地人工测试.cmd`。

首次启动可能需要获取既有依赖、镜像和 Chromium。启动本身不会访问官方来源或 Provider；只有
负责人在控制台保存 Provider 配置，并勾选“确认来源与硬预算”创建 `LIVE_OFFICIAL` 运行后，
后台 Worker 才会按所选来源和固定预算执行。

## 数据、身份和 Provider 配置

- PostgreSQL 使用当前工作树专属的 Compose named volume。正常停止只停容器，不删除该卷。
- 原始官方材料和 Provider 原始响应写入
  `%LOCALAPPDATA%\DeepAha\manual-test\objects` 的本地对象存储。
- Provider API Key 由 Windows DPAPI 加密后保存；API 和页面只返回配置状态，不能读回密钥。
- 首次配置可选择 Agnes 2.5 Flash、DeepSeek V4 Flash、DeepSeek V4 Pro 或自定义预设；
  系统一次只激活一套配置，旧运行继续保留创建时冻结的 Provider/模型快照。
- 后台 Worker 在实际调用前才解密密钥；启动脚本、命令行、环境变量和运行清单都不包含密钥。
- 本地 reviewer 是固定的非合成负责人身份；每次启动只轮换浏览器会话，不覆盖历史人工决定。
- 默认不灌入合成 Opportunity、画像、提醒或模型结果。首次启动后的 `runs` 和 `opportunities`
  都为 `0`，直到负责人创建真实运行。

停止并重新启动会保留官方材料、运行、人工决定、P9-B ModelCall/Ledger 审计、浏览器配置和
加密 Provider 配置。删除 Provider 密钥是控制台中的独立操作，不会删除历史审计。

## 受控真实运行

控制台把外部动作合并为一次与具体运行绑定的确认，而不是在每条内部状态转换时重复询问：

1. 选择已审核的官方 Source Recipe；页面展示官方 host、用途和请求上限。
2. 选择 `LIVE_OFFICIAL` 并确认固定官网/LLM 预算。
3. Worker 先采集官方公开内容；挑战页、认证、拒绝访问、内容类型或校验失败时禁止进入 LLM。
4. 确定性引导停在 `BOOTSTRAP_REVIEW`，由负责人查看来源和暂定 Opportunity 后继续。
5. P9-B Gateway 使用冻结 Provider/模型快照、最小化消息、完整请求身份和 Ledger 执行一次受控
   抽取；页面显示 token、延迟、费用状态和 hash，不显示原始响应对象或密钥。
6. 事实、规则和本地发布仍由负责人逐项批准。发布只进入 `LOCAL_HUMAN_REVIEWED` 本地目录，
   不等于 Gold、生产发布或 Release Qualification。

`OFFICIAL_REPLAY` 只复用该持久库中已经成功取得的同一 Recipe 官方证据，不访问官网；尚无可用
证据时会明确失败，不生成伪数据。

本地人工测试的模型输入只允许来自已审核 Recipe 的官方公开证据块，P9-B 分类固定为
`PUBLIC_OFFICIAL_GENERAL` 且 `contains_user_data=false`。Provider 可以采用经明确记录的临时保留
（`PROVIDER_TRANSIENT_RETENTION`）；零保留不再是公开资料测试的虚假必选项。真实出站仍要求
负责人确认 Provider 不将本次输入用于模型训练。零保留和 Provider 原生幂等能力只有存在明确
依据时才勾选，默认均为关闭。

本地人工体验阶段保留逐项批准，是为了检查证据和产品体验。未来正式运行不要求所有低风险字段
永久逐条批准；只有在相应 Release Qualification 和自动化质量门成立后，低风险结果才可按策略
自动流转。高影响资格规则、冲突、不确定和异常结果仍必须进入人工治理。

## 证据责任边界

真人参与者仍为 `0`，`Release Qualification` 为 `NOT_STARTED`。负责人本人的本地体验可以发现
交互和工程问题，但不形成设计伙伴的理解、信任、行动、留存、付费或生产发布资格证据。不得把
本地批准、一次实时模型响应或官方页面采集成功升级表述为 `STABLE`。

## 常见失败与恢复

- 缺少或未启动 Docker Desktop：启动 Docker Desktop 后重试。启动器不会重置 Docker Desktop。
- 缺少 uv、Node.js 24 或 Corepack：安装对应环境后重试。
- 端口被占用：启动器不会按端口终止未知程序；关闭明确占用者后重试。
- Provider 未配置、密钥不可解密或运行创建后配置发生变化：该 item 进入 `FAILED_CONFIG`，不会
  访问 Provider。
- Source 出现 403、登录、CAPTCHA、挑战页或内容校验失败：保留诊断和原始证据，禁止 LLM。
- Provider 结果未知：item 进入 `UNKNOWN_OUTCOME`，不得自动重试成另一调用身份。
- 启动中途失败：仅停止本轮已验证拥有的进程和容器，持久卷与 Provider 配置保留；日志位于
  `.deepaha-local-manual/logs/`。

停止入口可重复执行。运行清单记录 API、Worker、Web 和浏览器宿主的 PID、创建时间和固定命令
标记；停止前会再次核对进程和 Compose 标签。启动器不执行全局 Docker 清理，不停止其他项目，
也不读取 `文档2/LLM-API.txt` 或任何其他个人资料文件。

## 数据清空

当前控制台只开放独立的 Provider 密钥删除。完整数据清空按钮保持禁用，直到能够在数据库进程外
同时证明精确 Compose 卷、对象目录和运行所有权；不要用正常“停止”冒充删除。需要清空时应作为
单独受控维护动作实现和验收，不能扩大为 Docker 全局清理或删除个人资料。
