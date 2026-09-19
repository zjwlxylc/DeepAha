# v0.3.0 兼容范围与格式边界

## 已支持的输入
- GPT Scout v2.2系：`deepaha.source-intelligence.run.v2.2` Handoff，多文件或一层ZIP，可带State/Review。
- WB Scout：同一顶层schema，不同run_key/字段形态，完整WB-scout.zip，包括18个Handoff/State和研究附件。
- State是查引用与续跑的上下文，不能单独当新的来源交接包；Review不是结构化候选。
- JSON原文不改写；`source_graph_delta`列表/对象、Brief中英文键、显式文字包装的证据ID、score字段等只在投影里规范化。
- 相同namespace+candidate_key按一张卡片展示，保留所有版本；相同run不同字节阻断；同URL只提示身份关系。
- 裸域名、域名模板、微信/小程序、未知来源不是可执行HTTP入口；保留但暂缓，不擅自补https。

## 三个输出不能混用
| 输出 | 用途 | 现状 |
|---|---|---|
| 当前研究交接 `deepaha.research-handoff.v1` | 批审、原件、版本、研究候选交给主系统暂存适配器 | 本版已生成；主系统接收适配器仍属R2开发 |
| 原 `deepaha.source-intelligence.import-profile.v1` 等旧严格契约 | 原单批导入内核、演练及已集成的服务端 | 原内核未放宽；当前48份真实Handoff原样均不通过 |
| `deepaha.scout-feedback.v1` | 主系统真实事件回到Scout | 本版提供结构检查与未认证展示；发行方认证/生产联调未完成 |

原工具不是“坏了”，而是研究者实际产出与旧执行契约不匹配。本次把研究适配放在前面，而不是删除旧的必填字段/权限/事务检查来让绿灯变多。

## 包与嵌套
默认限制：输入100MiB、单ZIP成员50MiB、所有展开文件500MiB、10000成员、JSON8MiB、压缩比1000。嵌套ZIP附件按原件保留，不递归打开。拒绝越界/绝对/Windows危险路径、符号链接、大小写重名、加密和重复JSON字段。

工作台生成的交接ZIP用于传递与备份，不作为新的Scout输入重复累计。继续处理请打开“最近的本地审核”；跨电脑时先解压originals，再选择其中原始JSON/ZIP，Decisions.json作为历史意见保留，不自动冒充新操作者批准。工具遇到自身导出契约会明确停止，避免只读取GPT而漏掉嵌套WB包。

## 保留的旧功能
手工选择文件；原单批Tk窗口；原CLI预览/提交/回执；原服务端和事务；程序主动调用Codex取资料库文件。没有取消手动上传，也没有改成“让你自己给Codex敲指令”。

新版资料库取回支持JSON/ZIP，目录为/deepaha、/DeepAha网络资源、/DeepAha机会星图。用户机器必须真实安装Codex并具有Library文件工具。协议、事件和文件hash有本地测试，但真实账号权限与实际取回仍需用户环境验证。错误会显示，不会用摘要重写原件，不会猜私有ChatGPT下载API。

## 不包含
Windows免安装EXE；自动升级主项目；联网逐站验证89来源；PDF/Office语义复核；自动合并机构身份；自动入生产库/批准来源/启动WMA；自动签名认证反馈；原生App。以上不是本版已完成能力。
