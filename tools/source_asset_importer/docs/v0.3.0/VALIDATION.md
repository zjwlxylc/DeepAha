# v0.3.0 验证记录与发布边界
验证时间：2026-09-13；执行环境：Linux、Python3.13；不是用户Windows/生产环境。

## 实际执行

| 检查 | 结果 | 证据 |
|---|---|---|
| 原v0.2完整测试基线 | 89项，88通过、1跳过 | 原代码独立解压测试；跳过真实PostgreSQL |
| 当前全量unittest | **142项，141通过、1跳过，0失败** | `evidence/v0.3.0/26_full_suite_final.log` |
| Python wheel构建 | 退出0，无需联网安装依赖 | `29_wheel_build.log`；构建提示当前pip缓存权限不可写，不影响产出 |
| JavaScript语法、Python编译 | 退出0 | `27_syntax.log`，`node --check`与compileall |
| GPT30+WB18真实包离线回放 | 48批，164观察，89身份组，33附件 | `23_real_asset_audit.log`，重放脚本可核查 |
| GPT State父子SHA/大小 | 30/30通过 | 资产交付包baseline/State_Chain_Verification.json |
| GPT90主文件与已给清单 | 90/90通过 | Archive_Manifest_Verification.json；不是本轮90次新下载 |
| 真实回环HTTP服务 | 令牌、Host、Origin、跨站、路径、越权等8项测试通过 | tests/test_workbench.py；不连接DeepAha生产库 |
| 桌面/390px界面 | 真实资产选择、89对象显示、保存/撤销、筛选/版本、返回列表、无横向溢出、生成ZIP通过 | `28_browser_final.log`与browser/截图 |
| 审核导出成员验证 | GPT交接95个成员、综合交接96个成员逐SHA/大小通过 | 资产交付包evidence/Assisted_Bundle_Verification.json |
| 用户机器Codex/Library | **未验证** | 只执行本地协议/进程替身/文件边界测试 |
| PostgreSQL | **跳过** | 未提供隔离DSN、DDL授权和psycopg条件 |
| 主系统新研究契约接收 | **未实施/未联调** | 必须进入R2暂存适配，不能走旧严格profile旁路 |
| Windows启动与实际浏览器下载 | **未验证** | 无Windows环境；浏览器HTTP受策略限制 |

## 浏览器限制不能隐去
本环境Chromium被管理员设置为禁止全部URL导航。实际HTTP导航尝试返回ERR_BLOCKED_BY_ADMINISTRATOR，见15_browser.log。没有更改或绕过浏览器策略。

后续使用离线DOM+真实Application方法：本地HTML/CSS/JS在about:blank渲染，fetch、download、storage明确为测试替身。它证明控件、交互、布局以及应用方法配合，不证明真实浏览器HTTP传输/下载已闭合。下载生成的真实ZIP由Python逐成员核验；HTTP安全另通过实际127.0.0.1服务测试。这些证据合起来仍不能替代用户Windows端到端验收。

截图不是伪造“已上线”，页面中测试操作者明确写“自动化界面测试（不是真人批准）”。用户使用新包默认空工作台，不预置测试决定。

## 本轮发现并修复的真实问题
- WB中文说明/分号包装的证据引用被误认为单个长ID：增加显式ID拆分和未知引用保留测试，跨批链接修复。
- WB State使用candidates字段：仅按source_candidates读取会丢参考上下文，增加别名读取。
- 同run_key但不同字节的selected State可能被错误纳入已验证链：现在还比较被选State的实际SHA。
- 本地工作区内部存储路径链接可越界：初始化拒绝父路径/内部blobs/exports/数据库链接。
- 反馈事件空ID或无效时间：显式格式和时区校验，不仅检查外壳。
- 把导出的研究交接ZIP当新Scout包会产生部分重读：明确拒绝，并给出继续会话/原件重读方法，不静默丢WB嵌套包。

以上均有先失败、后修复、再通过的日志，18–25号为补充案例。早期red.log是TDD失败反例，不是当前未修复故障。旧v0.1/v0.2证据仍作历史保留。

## 自查范围
已对照五项用户任务、差异、输入安全、版本归并、回执真实性、旧契约隔离及导出原件保留复查。没有可用的独立代码审查子代理，本轮不声称取得“独立专家/独立模型审查PASS”。交给Codex的后续复核见REVIEW_HANDOFF.md。

结论：可交付本地试用的v0.3.0源码增量；不能称生产就绪或Windows已验收。真实系统反馈、主系统持久化、Source批准、WMA生产运行、附件语义和真人价值分别仍有独立验收门。
