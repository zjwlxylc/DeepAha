# v0.2.0：程序调用 Codex CLI 获取资料库文件

## 用户操作方向

**导入工具 → Codex CLI → 已授权资料库工具 → 原件文件 → 导入工具。**

不是“用户下载文件 → 打开 Codex → 让它运行导入器”。默认 GUI 增加“从资料库获取”，读取列表后选中一项取回，载入原界面；数据库预览和确认仍独立。

## 实际调用

调用器通过 `subprocess.Popen` 的参数数组、`shell=False` 启动本机 Codex。提示词通过标准输入，不通过 Shell 拼接；输出使用 JSONL 工具事件和结构化最终结果。

命令骨架（由代码生成，不要求普通用户手工输入）：

```text
codex --ask-for-approval never exec
  --skip-git-repo-check
  --sandbox read-only（列出）或 workspace-write（取回）
  --color never --json --ephemeral
  --output-schema <本轮schema文件>
  --output-last-message <本轮result.json>
  [--profile <用户已配置的名称>]
  [--model <用户选择的模型>]
  -c approval_policy="never"
  -c web_search="disabled"
  -c sandbox_workspace_write.network_access=false
  -
```

`never` 表示不在无人值守进程里等待审批，不是绕过沙盒。默认不启用 `danger-full-access`、`--yolo` 或自动安装/配置工具。取回阶段可由用户明确勾选网络下载，但不会增加资料库账户权限。

保留本机已有 Codex 登录和工具配置，不会自动创建 MCP 或插件。Windows 标准 npm `codex.cmd` 优先转换为对应 Node + `@openai/codex/bin/codex.js` 调用；不执行任意 cmd 字符串。非标准包装器无法识别时，提示选择原生程序或修复安装。

## 两次调用，职责分开

**list**：只列 `/DeepAha网络资源` 内 Handoff 文件。返回实际原生文件 ID、版本、大小、修改时间和可获得的远端哈希；未知字段保留 null。默认最多50，用户可调到200；尚未遍历完必须标记 `listing_complete=false`，不谎称“全部”。

**fetch**：根据本次已选择的 ID/版本再次确认目录归属，取回原始文件以及 `run_metadata.file_dependencies` 声明的依赖。Handoff 放在本轮 payload 根目录，依赖保留相对路径。只支持原件导出/复制，不使用模型生成的 JSON、OCR 或摘要重建文件。

最终 JSON 契约由 `library_pull.response_schema()` 生成，协议名为 `deepaha.library-pull.v1`；它是**本工具与 Codex 的任务输出协议，不是 OpenAI 资料库 API**。

列表和下载不同状态：`OK / NO_FILES / UNAVAILABLE / AUTH_REQUIRED / FOLDER_NOT_FOUND / AMBIGUOUS_FOLDER / EXPORT_UNAVAILABLE / FILE_CHANGED / FAILED`。

本工具额外区分：找不到 CLI、启动失败、超时、取消、缺少工具事件、路径不安全、实际文件不存在、哈希不匹配、旧导入契约不接受等情况。

## 校验及信任边界

代码要求成功的 `item.completed` / `mcp_tool_call` 事件元数据，且最终结果的 tools_used 与至少一项实际事件相符。然后核对本轮请求、目录、选择 ID/版本、文件存在、普通文件类型、安全相对路径、哈希/大小和原有 Package 契约。

重要：**工具事件只证明发生过调用，不能独立证明每个文件 ID、目录归属和语义判断都正确。**远端归属仍依赖已授权工具及 Codex 的报告；若列表无远端哈希，下载清单中的模型计算哈希只能与本地字节核对，不能伪装成平台签名。下载来源记录会明确这一限制。

当前兼容的工具事件格式是官方文档列举的 MCP JSONL 事件。若实际客户端的原生文件工具使用另一种事件格式，会返回 `LIBRARY_TRACE_UNVERIFIED`；需由 Codex 在实际环境扩展事件适配，不应直接删除检查。

单主文件8MiB、单依赖20MiB、总量64MiB，最多100个依赖。没有调用任何网页采集来补齐丢失依赖，不会修复原 Handoff 数据。未通过原导入格式校验的内容不载入；失败工作区会清理，不把它变成新资产。

模型工作区与持久下载区分开。校验成功后由宿主写入独立目录；保存目录清单和下载来源记录，不保存完整模型推理、命令内容或工具正文到运行日志。

启动进程时去除 `DEEPAHA_*` 和常见数据库凭据环境变量；主窗口导入 token 不传入提示词或进程参数。**这不是对同一 OS 用户的强隔离承诺**：Codex 的既有用户配置、hooks 和工具仍须可信。应使用仅有必要资料库读取权限的配置/OS环境；不得在该 Codex 配置下授予自动写生产库权限。

## 初次本机配置

普通用户在获取窗口保留 `codex` 即可尝试使用既有安装。配置保存在数据目录 `codex-library.settings.json`，参考包根目录 `codex-library.settings.example.json`。不含 ChatGPT 密码、Cookie 或 DeepAha token。

若已有专用 Codex 配置名称，可填入 profile；模型留空则沿用 Codex 自身配置。不假定某个不存在的 profile 名称已建好。

**不能仅写一个 MCP 服务地址就承诺能够读取原生 ChatGPT Library。**必须是实际提供该账户该资料库原件访问的工具；普通本地 filesystem MCP、Google Drive 和公开互联网搜索都不能冒充。若无实际通道，本功能会如实停在缺少工具/导出能力，不偷偷改变为手动下载方案。

## 命令行入口（面向开发接续）

```text
python -m deepaha_importer library-list
python -m deepaha_importer library-fetch --catalog <上一命令返回的catalog_path> --file-ref <清单中的真实file_ref>
```

两个命令都由程序自己启动 Codex，不接收 DeepAha 导入 token。取回命令只返回真实本地路径，不执行 import。

`--codex-config` 指向本功能的配置；`--codex`、`--profile`、`--model`、`--timeout` 可覆盖本次值。存在同 ID 多版本时使用 `--file-version` 明确版本。

## 官方实现依据

核查日期：2026-09-06。只查文档，没有实际调用用户 Codex。

- OpenAI Non-interactive mode：`https://developers.openai.com/codex/noninteractive/`（现重定向至 `https://learn.chatgpt.com/docs/non-interactive-mode`）。用于 exec、stdin、JSONL、output-schema、output-last-message、ephemeral。
- OpenAI CLI reference：`https://developers.openai.com/codex/cli/reference/`（现重定向至官方 Developer commands）。用于 sandbox、approval、profile、model 参数。
- OpenAI Model Context Protocol：`https://developers.openai.com/codex/mcp/`。用于区分本地 Codex 的工具配置与 ChatGPT 网页侧权限。

这些依据只证明调用机制，不证明用户账户已经具备原生资料库读取能力。

## 本轮未做

没有测试、没有实跑 CLI、没有取得真实 Library 文件、没有开通任何权限、没有回写资料库、没有接入正式 DeepAha。需要在真实本地环境继续确认上述条件。
