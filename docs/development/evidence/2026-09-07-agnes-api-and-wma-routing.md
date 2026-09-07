# Agnes 免费 API 与三路接入核验

核验日期：2026-09-07。用户选择 `agnes-2.5-flash` 是为控制开发成本，后续接入保留这一选择。

**用户最新明确的责任边界：WMA 模型由用户在 WorkBuddy 后台固定配置，不由 Codex 负责。** DeepAha 只调用该后台已发布 Agent，不指定或覆盖模型，不同步本地模型文件、URL 或密钥。下文模型服务与官方限制是本轮历史诊断证据，不构成后续模型配置任务。

## 当前结论

Agnes API 本身可用。本轮使用已有本地 WorkBuddy 自定义模型配置，向其原有 Agnes 地址发送一次最小请求，HTTP 200，返回模型为 `agnes-2.5-flash`，正常输出。未修改本地配置，也未把 Agnes 密钥上传到 WMA。净化回执见 [直接调用记录](2026-09-07-agnes-direct-api-check.json)。

WMA 发布会话的诊断则返回 `400 model [agnes-2.5-flash] service info not found`。这是本次 WMA 调用上下文未识别模型服务的证据，不是 Agnes 服务下线、免费额度耗尽或模型能力不足的证据。单次成功也不证明持续容量、工具调用和完整调查均通过。

## 官方限制

| 项目 | 查得内容 | 使用边界 |
|---|---|---|
| 当前价格 | 输入和输出均为 `$0 / 1M tokens` | 当前官方价格，不保证永久免费；不是 WMA 沙箱或积分费用回执 |
| 上下文 / 最大输出 | `512K` / `65.5K` | 模型上限；运行器仍可能有更小限制 |
| 免费文本速率参考 | 对外请求 30 RPM，实际可执行 20 RPM | 官方 FAQ 更新于 2026-06-28，可能调整；账户当前权限优先，不当作本账户实测限额 |
| 多密钥 | 同类型密钥共用限额池 | 创建更多免费 Key 不增加总额度 |
| 每日额度 | 未查得当前 2.5 Flash 免费账户的统一每日固定额度 | 不套用旧 2.0 模型或付费计划的数字 |

模型与价格来源：[Agnes 2.5 Flash 官方文档](https://agnes-ai.com/zh-Hans/docs/agnes-25-flash)。速率与密钥池来源：[AgnesAI-Labs Token Plan FAQ](https://github.com/AgnesAI-Labs/AgnesAI-Models/blob/main/docs/TOKEN_PLAN_FAQ.md)。官方文档明确可用性、速率和计费以账户/API Key 权限为准。本轮未做压测，也未探测额度上限。

开发阶段先用串行、明确范围的小样本校准。一次调查 prompt 内可能有多轮模型调用，不能把“每分钟一条调查任务”换算成“一次模型请求”；主仓时限和 prompt 次数限制不能强制 WMA 内部的模型 RPM。

## 三种接入分别判断

PoC 是 WMA、WorkBuddy CLI、Codex CLI 的完整对比程序，三路共享调查输入和交付目标，但运行地点、会话创建和模型参数传递不同。完整逐行核对见 [三路示例对照](2026-09-07-wma-example-comparison.md)。

- WorkBuddy CLI 的现存实现将配置模型放入请求；本地自定义模型的 URL 和密钥由本地运行环境处理。
- Codex CLI 的现存实现向会话和任务启动请求传递模型，其配置能力不能当作 WMA 的能力。
- WMA 的现存实现上传任务文件、创建默认会话、发送调查并回收产物，但没有消费 `cfg.model`。历史指标中的 `custom:agnes-2.5-flash` 是请求配置记录，无法单独证明实际模型。

WorkBuddy 官方明确说明，自定义模型参数及 API Key 只保存在本地 `workbuddy/models.json`，不上传云端。因此“本机手动测试正常”与“WMA 云端未找到同名服务”可以同时成立。[WorkBuddy 模型配置](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Model)

## 接入方向与未验证项

主仓继续复用 PoC 的上传、单次调查、回收和恢复方式，并修正发布 Agent 绑定、原件二进制保真和交付验证。模型由后台决定，不向 WMA 提交本地 `cfg.model` 符合用户确认的分工；它本身不是待修复缺陷。不能退回缺少发布配置的默认会话，仅以有输出宣称目标 Agent 已接通。

官方企业模型管理提供自定义模型名称、供应商模型 ID、部署地址和 API Key 配置，并有连接测试及可见范围。公开 OpenAPI 也区分企业注册模型 ID 与供应商原始模型名称。这些属于后台配置资料，由用户维护；本批不核对或修改企业注册、可见范围和模型引用，不补 `custom:` 前缀，不改付费模型。[企业模型管理](https://www.codebuddy.cn/docs/enterprise/adminguide/%E6%A8%A1%E5%9E%8B%E7%AE%A1%E7%90%86)、[官方 OpenAPI 定义](https://www.workbuddy.cn/apiDocs/api.yaml)

这说明存在官方自定义模型配置途径，尚不证明当前账户具备相应权限，或该企业配置会被当前 WMA 调用链直接使用。当前 WMA manifest 的 `settingsJson.model` 只包含模型选择，未发现自动读取本地 `models.json` 的接入步骤。[WMA API 定义](https://www.workbuddy.cn/apiDocs/agentos-api.yaml)

本记录没有执行云端模型注册、第三方密钥传递或 Agent 发布。后续 Codex 工作集中于调查提示、交付契约、原件保真、候选核验和内部审核。提示词候选也仍未发布。

## 历史产物的参考价值

历史数据库证实有实际运行和产物，适合复用场景、材料清单、反例和交付形状。[只读历史审计](2026-09-07-poc-history-audit.md) 同时发现，旧验证没有实际重算所有原件字节摘要；17 条 WMA 运行中，没有一条满足本轮“全部声明材料字节摘要相等”的检查。历史 `COMPLETE` / `OK` 不能直接当作 DeepAha 的正式事实验收。

这不否定程序已能输出；它明确了从实验输出进入可追溯事实还要补的验证。旧数据库和运行文件未改写。
