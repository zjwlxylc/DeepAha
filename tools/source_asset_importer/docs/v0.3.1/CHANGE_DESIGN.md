# 修改范围与能力边界

目标：把“无法判断为什么一直等待”的资料库入口改为有前置检查、真实证据、进度、可取消、可诊断的受控文件获取入口，同时保证已有审核和主系统调用边界不变。

## 三类故障不能混为一谈

1. 已确认的代码问题：未在启动目录任务前检查CLI；浏览器任务轮询无总上限；模态弹窗将外部取消按钮置于不可交互区域；无持久化、用户可导出的安全诊断。此次已修复这些可控制的问题。
2. 平台能力前提：本机CLI必须实际提供已授权的个人资料库目录与原件导出工具。程序启动成功、登录成功、Apps开关存在、模型自报成功均不是最终证据。此处不能靠新增本地代码创造未提供的远端权限。
3. 用户本机的具体触发原因：截图和交接ZIP没有该次Codex日志，因此缺CLI、授权、参数、配置、网络、额度、超时等不能凭截图二选一。本次尚未证明用户直连原件成功。

没有改为抓Cookie或浏览器私有API；没有安装插件、自动改账号权限、解除沙盒或强制降级验证。手动下载/文件夹选择依然可用。

## 调用结构

资料库路径：本地UI → 前置检查 → Codex exec → 实际已授权的资料工具 → 原件字节核对 → 本地审核。

业务路径：外部Scout → 原件/审核建议 → DeepAha R2候选暂存与真实回执 → 正式来源审核 → 有范围的公告发现 → 主项目显式调用Direct WMA → 材料和候选事实回收 → 核验发布。

Codex在这个工具中只搬运资料，不开展新的官方机会调查、不写生产库、不批准来源。WMA也不因本地点击“建议接收”而自动启动。旧单批兼容窗口保留，仍按原契约与权限工作，不接收新的research-handoff ZIP。

主仓比较范围仅为用户提供的DeepAha-main.zip，ZIP comment `d0918ec1245264e271f42a18d54c0fb903000c00`；未联网读取当前GitHub HEAD或生产部署。快照未包含scout_intake模块。现有api/investigations.py通过source_policy过滤来源，随后登记并显式发起调查；不能绕过该链路。

## 修改文件

- codex_process.py：只读CLI元数据探测、可选参数兼容、有限执行、取消、安全错误类别。
- research/library.py：连接与取回诊断，仍保留原件身份/哈希与真实工具记录校验。
- workbench.py：进度/取消状态与受本机会话令牌保护的诊断下载接口；配置变更清空旧目录清单。
- web/index.html、app.js、style.css：弹窗内的操作与结果、明确手工入口、完整审核空态。
- research/workspace.py：首次导出时间、最后审核时间、历史导出不可变复用。
- schemas/research_handoff_v1.schema.json：可选新增时间字段，保留原v1的附加属性兼容。
- 包构建：排除本地工作区、下载目录及诊断目录，避免运行后的私人资产进入源码包。

不修改分组算法、来源身份、批准规则、原件或外部研究结果。对用户WB原包再次运行后summary、来源对象与issues均与旧Audit一致。

## 官方资料与本次判断（2026-09-13）

- OpenAI Library说明： https://help.openai.com/en/articles/20001052-file-storage-and-library 。官方明确提供在资料库选择一个或多个文件后下载；该页没有给出适用于本机CLI的通用个人资料库读取API承诺。
- Codex非交互模式： https://developers.openai.com/codex/noninteractive 。支持exec、JSON事件、output-schema、output-last-message；本工具用这些控制执行和读取结果，不把“CLI官方支持”解释成“所有远端数据都可见”。
- Codex MCP： https://developers.openai.com/codex/mcp 。远端工具由实际运行环境和配置提供；并不等同ChatGPT这次对话的可用工具集合。
- 配置参考： https://developers.openai.com/codex/config-reference 。本地命令沙盒网络与Apps/MCP工具权限不是同一层；网络开关不能代替账号授权。文档当前apps为稳定能力、默认开启，所以本版没有简单强制添加apps=true来伪造修复。

上述官方文档用于能力边界，用户包统计来自本地audit_review_export.py，具体用户运行原因仍等待本机诊断；三者互不替代。
