# WMA 示例与三路模型传递对照

审查日期：2026-09-07。方式：只读源码、已落盘记录和本机已安装 SDK；未启动 PoC、未创建云资源、未发起模型或 WMA 请求。未读取或复制模型配置中的密钥、云标识及思考内容。

源码根：`D:\Agent\wb-agent-cli\deepaha-agent-poc`（以下 `PoC/`）。主交付根：`D:\DeepAha\.worktrees\delivery1-direct-wma`（以下 `Delivery/`）。行号对应本次读取时的文件。

PoC 当前 HEAD：`edc72cc62982503f36cd96726ad4f59c86f3947a`；本次以工作区实际文件为准，不将 HEAD 当作工作区完全干净的声明。

## 结论

用户在本次对照完成时进一步明确：WMA 模型由用户在 WorkBuddy 后台固定配置，不由 Codex 负责。因此 WMA 不消费本地 `cfg.model` 本身不是缺陷，也不需要迁移本地模型配置。下列审计用于区分三路参数和证据来源；主仓继续调用后台已发布 Agent，不覆盖模型。

1. PoC 的 WMA 实现确实包括凭据装载、Runtime/默认 Session、SOP 和 schema 上传、执行、超时/取消、结果及引用原件回收。此前若只看 Runtime 创建示例，会遗漏实际文件链路；本批主交付已具备这些文件传递步骤。
2. 在本次追踪的 PoC WMA 调用链及探针中，未发现读取或上传本机 `.workbuddy/models.json`、传递 Agnes 自定义服务 URL/API Key、或提交 `custom:agnes-2.5-flash` 模型选择的步骤。PoC 将这个模型名写进 WMA 的本地配置和统计，不能据此确认云端实际模型。
3. 企业示例的 `CODEBUDDY_API_KEY` 注入不是遗漏：当前两套 SDK 都会自动把 `CloudAgentClient.api_key` 注入 Runtime manifest secret。它传递的是已经提供的企业凭据，代码没有把本地 Agnes URL、专用密钥和模型配置转换为云端路由。
4. PoC 的 R1 技术设计明确将 WMA 自定义模型/Agnes 保持为 `UNVERIFIED`。后续报告直接称 WMA 使用 Agnes，与可检查代码和模型回执之间存在证据缺口。CLI 的自定义模型能力不能归给 WMA。
5. 当前主交付用发布 Agent 的数字标识创建专属 Session，并校验发布 manifest；这与 PoC 的 `sessions.default()` 不同。PoC 成功运行的历史不能证明它执行了当前发布 Agent 或 Agnes。

## 三条运行路径如何提交模型

共同入口：`PoC/app/cli.py:16–20` 或 `PoC/app/web/server.py:198–205` 调用 `prepare_run`；`PoC/app/services/investigation.py:50–59` 决定 `cfg.model`；`app/runners/factory.py:79–86` 选择独立 runner。`run_investigation` 在 `app/services/investigation.py:89–118` 完成提示、预检、启动、执行、用量和本地验证。

| 路径 | 本地模型值 | 实际提交位置 | 配置与环境边界 |
|---|---|---|---|
| Codex CLI 二进制的 app-server 接口 | 默认 `gpt-5.6-sol`，显式模型可覆盖；`PoC/app/config.py:24–25` | `PoC/app/runners/codex.py:141–143` 放入 `thread/start.model`；`160–165` 再放入 `turn/start.model`，并可传 effort | `111–124` 启动独立本地子进程和运行工作目录；`134–139` 使用 ephemeral thread。`51–58` 复制父进程环境并覆盖代理，没有建立独立 `CODEX_HOME` 或清除其他凭据变量，因此只能认定子进程/工作目录/会话隔离，不能认定凭据和全局配置彻底隔离。 |
| WorkBuddy Enterprise CLI | 默认 `custom:agnes-2.5-flash`；`PoC/app/config.py:27–29` | `PoC/app/runners/cli.py:407–418` 把 `cfg.model` 写入本地网关 `POST /api/v1/jobs` 的 `model` | `162–183` 复用或启动本地 codebuddy `--serve`；启动时复制父环境并按需设置 `CODEBUDDY_API_KEY`。该路径使用本机 CLI；它与 WMA 云沙箱并非同一进程。 |
| WorkBuddy WMA | `prepare_run` 同样给 WMA 填入 `custom:agnes-2.5-flash` | **WMA runner 没有消费 `cfg.model`**。`PoC/app/runners/wma.py:806–816` 构造的 PromptOptions 仅含回调、超时和取消参数 | 凭据来自 `SecretConfig`；`PoC/app/services/secrets.py:114–135` 读取企业 key/source_app/Agent id 及 CLI 凭据，没有读取 models.json、模型 URL 或提供商配置。 |

Codex 的二进制路径虽然位于本机 WorkBuddy 管理的 Node 安装目录（`PoC/app/config.py:11–15`），但启动的是 Codex `app-server --listen stdio://`，不是 WorkBuddy CLI 的 Jobs 接口，更不是 WMA。不能按安装目录归并三路模型能力。

## PoC WMA 的完整调用顺序

1. `PoC/app/services/investigation.py:87–106`：构建调查提示、工厂选中 WMA、preflight、start、run_turn。
2. `PoC/app/services/secrets.py:114–135`：企业凭据从环境读取，缺失时从指定凭据文件读取；只形成 `SecretConfig`，无本地模型配置同步。
3. `PoC/app/runners/wma.py:209–218`：检查凭据，调用 `_create_runtime_and_session`。
4. `PoC/app/runners/wma.py:239–268`：创建 `CloudAgentClient(api_key, source_app)`，可增加 HTTP 读超时；构造仅 id/name/version 的 manifest，调用 `runtimes.create`。
5. `PoC/app/runners/wma.py:270–275`：取得 `rt.sessions.default()`。没有调用 `sessions.create(agent_id=...)`，也没有读取发布版本进行会话 manifest 校验。
6. `PoC/app/runners/wma.py:454–508`：`_upload_skill_schemas` 的上传候选固定为 `SCHEMA_OPP`、`SCHEMA_EVID`、`SKILL_PATH`；用 SDK 返回的数据面地址和 ACP token，向 `/files?path=...` multipart 上传。具体候选文件定义在 `PoC/app/services/prompt_builder.py:11–13`。列表中没有 models.json 或模型配置文件。
7. `PoC/app/runners/wma.py:540–559`：先上传，再进入有并发限制、退避和超时的执行段。上传失败在旧 PoC 中仅告警，不会阻断。
8. `PoC/app/runners/wma.py:580–662`：遇到部分异常时，重新获取默认 Session 后重试；此段仍没有模型配置或模型选择步骤。
9. `PoC/app/runners/wma.py:735–820`：订阅消息和状态，构建 `PromptOptions(on_chunk, timeout_ms, cancel)`，执行 `session.prompt` 并检查 stop_reason。
10. `PoC/app/runners/wma.py:684–694`：正常结束后进入数据面回收；`341–452` 下载三件套及 evidence 引用材料，落到本地，再由上层 Verifier 检查。旧实现对部分原件用文本读写回收；主交付已改成字节处理，不应为了模仿 PoC 退回文本转码。
11. `PoC/app/runners/wma.py:865–872`：返回已收到的用量或明确不可用；`957–968` 关闭本地 SDK/HTTP 客户端。没有在收尾阶段注册或上传自定义模型。

## 企业示例、SDK 和探针核对

企业 REST 示例 `PoC/docs/vendor/workbuddy/wma/enterprise-api-example.md:28–34` 包含 `CODEBUDDY_API_KEY` secret；同文 Python 示例 `64–74` 没有显式重复它。完整 R1 证据文件对应 `DAIL_v1.1.2-R1_WMA_Enterprise_Instance_Integration_Evidence.md:59–68` 和 `122–142`。

这一区别由当前本机 SDK 解释：

- `cloud_agent_sdk/client.py:42–93` 的 `_inject_api_key_secret` 把客户端企业 API key 作为 `CODEBUDDY_API_KEY` secret；`144–176` 在 Runtime 创建时调用它。
- `cloud_agent_sdk/runtime.py:44–70` 区分普通 Runtime Session 和携带 `agent_id` 的发布 Agent Session；后者使用 `/agents/sessions`。
- `cloud_agent_sdk/opts.py:364–365` 虽声明 `include_thinking` 和 `model` 字段，但当前 `session.py:243–245` 只向 ACP 层传会话、文本块和取消事件；`acp/client.py:381–384` 最终只调用 `prompt(session_id=..., prompt=...)`。因此仅在调用侧添加 `PromptOptions.model`，并不能从这份 SDK 代码证明模型选择已传到云端。

SDK 对照位置：

- PoC 启动脚本 `PoC/start_web.sh:25` 指定的 `C:\Users\LENOVO\.workbuddy\binaries\python\envs\default\Lib\site-packages\cloud_agent_sdk`。
- `Delivery/backend/.venv/Lib/site-packages/cloud_agent_sdk`。

本次静态校验两处 `client.py`、`runtime.py`、`session.py`、`opts.py` 的 SHA-256 分别完全一致。该结果证明当前两套安装副本相同，不追溯证明历史每次运行时都没有变更。

| 已追踪的 PoC 探针 | 实际探测范围 | 与自定义模型的关系 |
|---|---|---|
| `_probe/wma_raw_runtime_probe.py:94–111`、`wma_dataplane_probe.py:117–145` | Runtime 响应、数据面链接 | 只注入企业凭据和 manifest；没有模型配置同步 |
| `_probe/wma_dataplane_proxy_probe.py:44–50`、`wma_dataplane_auth_probe.py:87–104` | 控制面/数据面的鉴权和路径矩阵 | 企业 API key 与 ACP token 的鉴权试验，不是 Agnes 服务路由配置 |
| `_probe/wma_dataplane_file_probe.py:81–125`、`wma_dataplane_path_probe.py:67–109` | 文件接口路径、方法和鉴权 | 无 models.json 上传 |
| `_probe/wma_dataplane_final_probe.py:59–62,79–116` | multipart 上传、下载及字节比对 | 历史结果 `_probe/dataplane_final_probe_result.json` 为 `FILE_SYNC_OK`，证明文件数据面，不证明模型身份 |
| `_probe/wma_nested_upload_probe.py:20–21,34–54` | 上传固定小型 schema 测试 JSON，验证多级目录自动创建 | 上传的是探针内容，没有完整模型配置或服务密钥 |
| `_probe/probe_wma_timeout_cancel.py:126–144` | 默认 Session、连接、超时/取消和断流 | 未提交模型名、模型 URL 或自定义提供商设置 |
| `_probe/build_openapi.py:21,202` | 本地 CLI Jobs API 的协议记录 | model 字段归属 CLI，不能作为 WMA 支持证据 |

## 历史记录能证明什么

`PoC/runs/wma-zjhr#4/result/metrics.json:6` 确实写有 `custom:agnes-2.5-flash`；但生成代码 `PoC/app/services/investigation.py:122–134` 直接将 `cfg.model` 写入 metrics，并非来自云端模型响应。该记录 `8–11` 同时显示用量不可用，provenance 仅记录 SDK 版本等信息，没有实际模型字段。

本次对 `wma-zjhr#4/events_normalized.jsonl` 仅解析元数据类事件，未输出思考文本；共找到 44 条 `wma/session_info_update` 或 `wma/usage_update`，非空 detail 数为 0，未提供可用于确认模型身份的回执。`wma-zjhr#3` 的 metrics 同样为请求配置模型名及不可用用量。

因此，`PoC/docs/v1.1.2/runtime-evaluation-report.md:15,36–37` 将 WMA 直接列为 Agnes、免费档的表格不能升级为模型已确认。更早且明确的边界仍在：

- `PoC/docs/DeepAha_DAIL_v1.1.2-R1_MD_Pack/DeepAha_DAIL_v1.1.2-R1_WorkBuddy_Runtime_Evaluation_Technical_Design.md:546–554`：WMA 自定义模型/Agnes 为 `UNVERIFIED`，不能据此建立生产成本假设。
- 同目录 `DAIL_v1.1.2-R1_WorkBuddy_Mandatory_Official_References_for_Codex.md:307,315`：CLI 自定义模型能力与 WMA Agnes 待验证项分开记录。
- `PoC/docs/vendor/workbuddy/wma/enterprise-api-example.md:120`：WMA 主路径 Agnes/custom model 为 `VERIFY`。

## 主交付有无遗漏

| 步骤 | 当前主交付证据 | 对照判断 |
|---|---|---|
| 企业 API key 与 SDK manifest secret | `Delivery/backend/src/deepaha/investigations/wma.py:121–126,202–216`，配合上述 SDK 自动注入 | 没漏掉示例已实现的企业凭据注入；它不等于本地自定义模型路由同步 |
| SOP/schema 和任务上传 | `Delivery/backend/src/deepaha/investigations/prompt.py:17–21,66–98`；`runner.py:82–93` | 已保留并严格限定文件清单，没有漏掉 PoC 的 schema 预置 |
| 数据面上传和原件回收 | `Delivery/backend/src/deepaha/investigations/wma.py:265–305,355–380`；`runner.py:99–108` | 已保留数据面，并采用字节及长度限制 |
| 当前发布 Agent 的实际 Session 绑定 | `Delivery/backend/src/deepaha/investigations/wma.py:222–237`；`168–182` 校验会话 | 已补足 PoC 未实现的发布会话绑定和验证，不能与默认 Session 混为一谈 |
| Agnes 自定义模型路由 | PoC 和当前迁移代码均未找到本地 models.json → 云端服务 URL/密钥/模型选择的映射实现 | 不是漏迁一个已经被示例证明有效的步骤，而是原示例本来就没有给出该闭环 |

主任务本轮提供的新实测事实为：本机 Agnes 配置直连返回 HTTP 200，返回模型为 `agnes-2.5-flash`；正确绑定发布 Agent 后的 WMA 会话拒绝该模型，列出调用账号支持模型。本只读子任务没有重发这些请求。这两个结果应分别记录：前者证明该直接 API 请求成功，后者是当次 WMA 未找到模型服务的运行结果，不能相互覆盖，也不能据此认定后台具体配置缺陷。

本报告不建议改模型名、增加 `custom:` 前缀、复制模型文件或替换密钥。按用户最新分工，模型配置不再进入 Codex 的后续任务；模型回执不可用时如实留空，不新增审批门，不用推定值替代实际遥测。
