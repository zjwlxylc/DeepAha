# DeepAha 来源资产导入工具 · 源码交付 v0.1.0

**这是一份可运行的源码包，不是已经部署到 DeepAha 的正式功能，也不是免安装 Windows EXE。**

实现依据：`docs/baseline/DeepAha_Scout_新版使用与导入方案_v1.0.md` 及 Scout v2.2.1 完整提示词。原文件保留在包内，没有重新改写它们。

## 你现在怎么试用

本机需要 **Python 3.11 或更高版本，并包含 Tk 图形组件**。客户端、核心逻辑和本地演练不需要第三方 Python 库，也不需要 Codex、模型 Key 或数据库密码。

1. 解压整个 ZIP，保留文件夹结构。
2. 在 Windows 双击根目录的 **`启动来源导入.cmd`**（英文同义入口 `launch_windows.cmd`）。
3. 保持“本地演练”选中，点 **“载入演练样本”**。
4. 点 **“预览（不入库）”**，检查来源、采集建议、证据及其他资产。
5. 点 **“确认并导入”**，在确认框核对环境和批次。
6. 点 **“打开结果目录”** 查看程序生成的 JSON 回执和阅读版回执。

演练样本是合成数据，使用 `example.org`，不是已经调查或批准的官方来源。演练只写本机 `demo.sqlite3`。**不要把 DEMO/TEST/STAGING 回执当正式反馈上传给 Scout。**

Windows 默认工作目录：`%LOCALAPPDATA%\DeepAhaSourceImporter`。其他平台为 `~/.deepaha-source-importer`。结果在该目录下 `receipts/`，配置在 `settings.json`；不会写入你的 DeepAha 生产数据库。

如果未安装 Python，启动入口会失败；这不是打包好的 EXE。后续可由 Codex 在你的 Windows 环境安装/检查运行环境，或单独制作安装包。不要从未知网页复制“修复命令”。

## 正式使用前，Codex 还要接哪一段

**本地界面、HTTP 客户端、统一导入服务和参考仓储已经有程序实现。尚未完成的是与实际 DeepAha 仓库的模型、账户权限、服务器部署和正式来源批准的联调。**

请把整个源码目录交给 Codex，先阅读 **`docs/CODEX_HANDOFF.md`**。不是让它重新写一个导入器，也不是把参考表直接当成第二套正式 Source Registry。

联调完成后，本地窗口取消“本地演练”，填写 Codex 核实后的服务地址/环境，并在本机提供导入授权。**程序中没有写死你的域名、数据库地址或任何密钥。仅填写一个地址不会自动让未部署接口变成可用。**

本窗口第一版只做“接收来源情报”。来源正式启用走 DeepAha 已有审核入口。服务层与 CLI 已提供独立批准参数和宿主批准回调，只有实际接通并获得相应权限后才可使用；默认拒绝，绝不伪造“WMA 已启用”。这与原方案的“可在同一次交互批准”兼容，但没有在本工具内重建正式审批系统。

## 实现内容

| 部分 | 代码位置 |
|---|---|
| 中文桌面窗口、后台线程、不挡住确认按钮 | `deepaha_importer/gui.py` |
| CLI：validate / preview / import / commit / receipt | `deepaha_importer/cli.py` |
| Handoff v2.2 读取、类型、引用、大小、安全路径、附件哈希 | `deepaha_importer/contract.py` |
| 只读预览、人工确认、整批入库、回执回读 | `deepaha_importer/service.py` |
| 权限、短期确认签名、身份/目标/动作绑定 | `deepaha_importer/security.py` |
| SQLite 演练与 PostgreSQL 参考暂存仓储 | `deepaha_importer/repository.py` |
| 独立批准的宿主接口与默认拒绝实现 | `deepaha_importer/integration.py` |
| 受控 HTTP API / 可挂载 FastAPI 路由 | `deepaha_importer/http_api.py` / `fastapi_adapter.py` |
| HTTPS 客户端、拒绝重定向、结果不明时查询回执 | `deepaha_importer/client.py` |
| 本地请求记录、JSON/Markdown 回执、安全保存 | `controller.py` / `receipts.py` |
| 测试、合成样本、规范、迁移参考、验证证据 | `tests/` / `examples/` / `schemas/` / `docs/` / `evidence/` |

## 命令行示例

在解压目录执行；下面示例不会联系真实服务器：

```bash
python -m deepaha_importer --help
python -m deepaha_importer validate examples/demo_Handoff.json
python -m deepaha_importer preview examples/demo_Handoff.json --demo
python -m deepaha_importer import examples/demo_Handoff.json --demo
python -m deepaha_importer receipt examples/demo_Handoff.json --demo
```

交互导入会要求你输入本次批次与环境的完整确认语句；其他输入都取消，不采用一律 `--yes` 的方式。

分开保存预览与确认：

```bash
python -m deepaha_importer preview examples/demo_Handoff.json --demo --output preview-local.json
python -m deepaha_importer commit examples/demo_Handoff.json --demo --preview preview-local.json --confirm-run demo-20260906-001
```

确认令牌有效期默认 10 分钟，预览文件仅供本机使用，不上传资料库。文件、依赖、数据库版本或动作发生变化必须重新预览。

## 重复、冲突和中断

同批次同内容再次导入返回原回执，不重复建来源；同批次不同字节拒绝。不同批次仍按候选键、精确机构与入口身份及历史入口别名去重。

有结构或引用错误不补造；有版本冲突整批不写。新增来源、Brief 新修订、关系和维护建议默认都只是待审核情报，不替换生产有效版本，不创建 VerifiedFact/OpportunityVersion，不触发 WMA。

网络中断时优先点“查询 / 恢复回执”。服务器可能已经完成，不能把没有拿到结果说成失败，更不能换批次盲目重传。服务器已成功而本机保存失败时也会单独提示。

回执由程序生成；**是否回传“DeepAha网络资源”由你决定**，不回传不阻止入库或既有采集。工具不会自动读写 ChatGPT 资料库。

## 验证与边界

真实结果见 **`evidence/final_verification.json`** 和 **`docs/IMPLEMENTATION_STATUS.md`**。

这里验证的是本代码的本地逻辑、SQLite 事务、真实本机 HTTP 请求、可选 FastAPI 路由及 Linux 虚拟显示下的 Tk 操作。**实际 Windows 双击、真实 DeepAha、真实 PostgreSQL、生产权限、WMA 消费链尚待联调。**

```bash
python -m unittest discover -v
# Linux 无显示器时验证窗口：
xvfb-run -a python -m unittest discover -v
```

测试不需要互联网。可选 FastAPI 测试缺依赖会明确跳过；PostgreSQL 测试必须另行提供隔离测试环境并显式允许，默认不运行。历史 RED 日志是实现前/修复前的证据，不代表最终仍有那些失败。
