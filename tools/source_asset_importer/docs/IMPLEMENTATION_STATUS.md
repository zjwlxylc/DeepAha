# 实现与验证状态 · v0.2.0

## 本次源码改动

在用户给出的 v0.1.0 ZIP 上增量修改，增加程序调用 Codex CLI 的资料库列表、选中文件取回、本地校验与载入入口；保留原来的导入业务逻辑。版本号升级为 v0.2.0，不覆盖旧 ZIP。

新增三份源码：`codex_process.py`、`library_pull.py`、`library_window.py`。同步接入中文窗口和命令行，更新版本、打包排除项及文档。

## 本轮验证状态

用户明确要求“只需增加功能，无需测试”。本轮**没有执行**单元测试、回归测试、GUI 运行、源码编译测试、Codex 实际调用、资料库实际导出、Windows 原生验证、PostgreSQL 或 DeepAha 联调。

因此本轮状态：**SOURCE_IMPLEMENTED / TESTS_NOT_RUN / LIVE_LIBRARY_NOT_VERIFIED / DEEPAHA_NOT_INTEGRATED**。

只进行了源码阅读与修改，以及文件打包、清单记录；不把这些动作描述为运行验证。

## 实际仍依赖的外部条件

1. 本机已安装/登录 Codex CLI，并且其实际工具能够读取和导出目标 ChatGPT 个人资料库原件。
2. 当前 CLI 支持本包使用的非交互参数与 JSONL 事件。按官方文档实现，不在本轮声称已通过具体安装版本验证。
3. 原 v0.1.0 的真实 DeepAha 数据模型、账户、服务端接口与批准边界完成接入。

若没有资料库工具，程序返回明确的能力缺口。写了调用代码不会让平台自动产生权限，也不能把仅有搜索摘要的工具当成文件导出工具。

## 历史证据隔离

`evidence/final_verification.json`、旧日志、旧窗口截图均为 **v0.1.0** 历史资料，未用于证明 v0.2.0 可运行。原实现状态保存在 `docs/baseline/IMPLEMENTATION_STATUS_v0.1.0.md`。

新增代码不包含真实账号、密钥、来源资产或用户数据库。没有导入/导出真实资料，没有执行部署。
