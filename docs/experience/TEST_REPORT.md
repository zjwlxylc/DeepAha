# DeepAha 机会星图｜分阶段体验改善开发与验证报告

交付标识：**experience-84353c7-20260920**。源码基线：`84353c7e5286e276d24af8e0342d4d3441c30ec5`。报告日期：2026-09-20。

## 一、交付结论

这是在指定仓库上修改、测试和整合的**完整系统源码**，不是独立交互原型，也不是仅含修改文件的补丁。A0–A3、B1–B3、C1 的工程实现已整合；D1 的真人任务、记录表、验收与发布清单已交付。**真实 WMA 调用及 2/4 并发、真实 PostgreSQL 升级/并发/恢复、真人验收和生产发布没有执行，不能把本包称为已经完成正式上线验收。**

本轮未推送或合并 GitHub，未修改正式站、隔离 staging、Nginx、Ops Gateway 和宿主凭据。个人数据库与原件数据目录不在源码包内。

## 二、分阶段落地内容

| 计划 | 实现结果 | 核心实现与证据 |
|---|---|---|
| A0 | 局部视觉组件、导航、空态、按钮、弹窗与焦点管理；320/390/1440 页面检查；保留原图形 LOGO | experience.css、core.js、浏览器页面记录 |
| A1 + B2 | 画像只提交修改项，未出现字段保留，显式清空；服务端版本校验，冲突后保留草稿、显示差异并经用户确认合并；旧 PUT 继续兼容 | profile-editor.js、personal.py、test_experience_api.py |
| A2 | v22 三海报首屏与原末尾品牌区；取消中间解释屏；总览筛选→详情→返回保留条件；资格、推荐理由和时间状态分开；六状态行动看板与列表 | home.js、user.js、actions-ui.js、test-experience.mjs |
| A3 | 整份返回只做整体通过/不通过；一般备注与硬阻断区分；旧 preview_hash、幂等和撤回版本保护保留；手机可读工作台，写操作转电脑 | workbench.js、原审核/权限回归、手机浏览器检查 |
| B1 | 服务端全量来源/任务搜索、状态筛选、分页、真实总计；来源详情、远程选择、任务详情、恢复文件与重新调查分开 | experience.py、operations-ui.js、120 来源用例 |
| B3 | 个人准备事项持久化、用户/目标隔离、幂等与版本冲突、来源标注；导出/清除完整；消息未读筛选和当前页批量已读 | preparation_items、消息接口、API/HTTP/浏览器用例 |
| C1 | 宿主命名连接、可信发布绑定、串行默认、验证后并发、预算/队列/域名上限、事务领取与租约、阶段记录、恢复不重发 prompt；受控真实实测命令 | dispatch_policy.py、worker.py、live_validation.py、20 项调度与实测保护测试 |
| D1 | 真人任务方案、空白记录表、分批放行与回退方案 | HUMAN_ACCEPTANCE.md、human_acceptance.csv、RELEASE_AND_ROLLBACK.md |

既有资格判断与推荐价值算法没有被前端原型的简化模型替代；审核仍不恢复逐字段人工批准。WMA 只生成候选内容，不能自行发布机会。Scout 资产和 WMA 返回的手工上传方式保留。

## 三、本轮实际运行结果

| 检查 | 实际结果 | 证据位置 |
|---|---|---|
| 修改前产品基线 | 245 项通过 | evidence/experience/baseline_product.log |
| 最终完整产品测试集 | **276 通过、2 跳过、0 失败、0 错误**，共 278 项 | evidence/experience/release-verification/product-full.xml 与 verification.json |
| 按文件再次执行 | 37 个产品测试文件，返回码全部 0；其中 PostgreSQL 文件的 2 项仍为跳过 | 同目录每文件 XML/log |
| Python 语法编译 | 通过 | 同目录 compileall.log |
| 6 项 Node 检查入口 | 全部返回 0：product、SG7.1、SG7.2、生日、核心渲染、体验改善 | 同目录对应 .log |
| 浏览器页面 | **87 个页面×宽度组合**，宽度 1440/390/320；各一个 H1，无页面级横向溢出 | portable-browser-final/browser-full-final.json |
| 浏览器交互断言 | **31 项通过**；另有 2 项末尾按钮 hover 样式观察，不与断言数量相加 | 同上 |
| 浏览器异常 | JavaScript 错误 0、异常 HTTP 返回 0 | 同上 |
| 真实 HTTP 联调 | **29 项通过**；独立临时数据库和实际 loopback TCP/HTTP | http-smoke-final/http-smoke.json |
| SQLite 增量升级 | 备份先行、五表新增、重复执行、已有账号与数据保持、运行任务拒绝、旧 Worker 回退代际阻断等用例通过 | test_experience_upgrade、test_sg8a_deployment 等 |
| 首页素材核对 | 原 LOGO 与基线字节一致；9 个海报变体与上传 v22 原文件哈希一致 | asset-origin.json |

最终验证脚本共记录 **45 个执行阶段**。全量运行和逐文件重跑是两轮相同测试，**不能把它们相加宣传为 552 个独立测试**。统计范围是当前 pyproject 配置的 `backend/tests/product`；仓库中保留的更早阶段代码与历史测试不等于本轮全部重新运行。

### 浏览器证据的精确边界

当前容器管理策略拦截原生页面导航，连本机地址也不能直接导航。本轮没有修改浏览器策略或生产 CSP。浏览器验证使用测试专用虚拟 location 与模块副本，执行真实 DOM/JavaScript/CSS，通过实际 HTTP 桥连接隔离数据库；测试副本和桥接逻辑只在 `scripts/experience`，不进入产品页面。页面内容并非静态假图，保存/冲突/查询/清单等实际调用后端。

因此这些结果证明的是**页面渲染、交互及应用接口联调**，不是原生浏览器 Cookie、正式 HTTPS、原生导航或实体手机验收。另行运行的 29 项 HTTP 检查是真实 socket 通信，但也不等于生产 TLS 验收。87 个组合是 29 个页面在 3 种宽度下检查，不是 87 个不同功能模块。

### 本轮发现并修复的问题

首先通过失败用例发现并修复：局部画像覆盖、版本冲突、全量来源查询、清单持久化/隔离、原子领取和调度限制。随后自查修复了租约过期后的迟到写入、耗时解析阻塞心跳、实测期间普通调度竞争、实测客户端创建/清理失败、远端状态不明后的保守占用等边界。弹窗 Tab/Shift+Tab 循环曾跳出到浏览器边缘，已增加明确首尾焦点循环并重跑通过。

旧 `RELEASE_COMPATIBILITY.json` 的代际若不更新，会允许旧 Worker 在新数据上运行，忽略新增策略与租约。本次把代际追加 `-experience1` 并禁止自动跨代回退，新增反例测试后通过。

历史失败日志保留，不覆盖成全绿。少量旧前端测试原来硬性要求已经被批准删除的首页中间屏、旧文案或单文件实现；现已更新为新页面结构和相同业务保护。原 SG8-A 的“本阶段没有 schema 变化”断言也按本次五表增量扩展更新。未删除原权限、审核幂等、资格和时间风险验证。

本轮只有执行者自查和自动回归，**没有另一个独立审查者或真人提供签字验收**。

## 四、WMA 能做什么，哪些尚未放行

AGENS/Agnes 连接强制串行；模型未知或没有当前绑定真实实测回执的连接也保持串行。修改 Agent、发布版本或绑定会使旧并发依据不再适用。前端不能通过提交 `verified=true` 获得权限。

宿主可用本包命令逐级验证 1→2→4，必须明确调用数量和预算。实测使用独立会话、生成带哈希的文件记录与实际重叠请求时间，成功后由受控宿主流程保存依据。实测占用同一数据库的调度保护；其他数据库/第三方对同一供应商账号的调用仍需宿主自行停掉。未知远端或中断实测不会自动释放并再次发 prompt，需先核实本地及远端都结束，再运行带理由的解除命令。

**这些是已实现、用隔离替身验证的控制逻辑；本轮没有运行真正 WMA 请求，未证明任何供应商实际允许 2/4 并发，也未证明实际语义提取准确率。**运行中的远端任务不会因为关闭新调度而被系统假称“已经取消”。

## 五、环境限制及真实验收缺口

本轮使用已有 Linux 容器（Python 3.13.5、Node 22.16.0）。基础锁定的 FastAPI、SQLAlchemy、Pydantic 等版本匹配，但 **WMA SDK 0.3.4 未安装**。`pyproject.toml` 声明 `pypdf>=6,<7`，本容器实际 5.9.0；尝试在线补齐没有成功，原声明没有被降低来伪装一致。旧启动器 requirements 与 pyproject 的 pypdf 声明差异保留为明确发布前检查项，见 RUN_AND_UPGRADE.md。

所以本轮不是严格的全新目标依赖安装验证，也不能把部分依赖匹配说成“全部环境一致”。后续在目标环境安装声明依赖后，须重跑产品回归及 PDF 证据用例。

| 未执行项 | 状态与原因 |
|---|---|
| PostgreSQL 实机升级、空库恢复与并发 | NOT_RUN；无隔离 PostgreSQL，2 项专用测试跳过 |
| 真实 WMA 单任务和 2/4 并发 | NOT_RUN；无实际 SDK/凭据与已批准预算；未发出调用 |
| Windows 原生安装、实体 Android/iOS 手机 | NOT_RUN；本容器不是这些环境 |
| 原生浏览器生产 HTTPS/Cookie | NOT_RUN；桥接 UI 和本地 HTTP 不能替代 |
| D1 真人任务和用户效果 | NOT_RUN；只交任务与空白记录，不虚构完成率/访谈 |
| GitHub 推送、合并、正式/隔离 staging 发布 | NOT_RUN；本轮只交付源码包 |

## 六、复现与使用

在完整包根目录运行，测试依赖按 `backend/pyproject.toml` 的 test 组准备：

```powershell
$env:PYTHONPATH = "$PWD\backend\src"
python scripts/experience/verify_manifest.py
python scripts/experience/verify.py --output .qa/verification
python scripts/experience/http_smoke.py --output .qa/http
python scripts/experience/browser_check.py --output .qa/browser --transport native
```

浏览器检查需安装 Python Playwright 和 Chromium，必要时用 `--chromium` 指定浏览器。当前容器实际运行的是显式 `--transport bridge`；该选项用于受限环境 QA，不能被写成原生浏览器验收。全部 QA 使用独立临时数据库，不启动采集 Worker，不导入正式用户数据。

本地试运行命令：`py -3.13 scripts/launch_product.py --install`。先解压到新目录，停掉旧进程，保留原数据目录；建议先用单独的 `DEEPAHA_DATA_DIR` 试运行。正式数据库升级、账号保留、备份及回退细节见 RUN_AND_UPGRADE.md 和 RELEASE_AND_ROLLBACK.md。

## 七、打包核验说明

完整源码包保留基线功能与历史文档，新增本轮代码、测试、说明和证据。交付排除 `.git`、缓存、虚拟环境、运行数据库和凭据，不附字体文件。`FILE_MANIFEST.json` 与 `.sha256` 为本次重新计算；清单不包含自身及配套 SHA 文件，避免循环哈希。

源文件扫描发现一份基线负例测试语料含禁止的密钥样式字符串；它与基线字节一致，供安全拒绝测试使用，不是运行密钥，分类记录于 package-preflight.json。本轮没有宿主真实秘密作精确比对，故不声称完成独立安全审计或“真实密钥精确零命中”。

最终 ZIP 的 CRC、文件清单、重新解压后的运行结果与 ZIP SHA-256 记录在下载包旁的 `PACKAGE_RECEIPT.json`；该回执单独保存，避免让 ZIP 把自己的哈希包含进自身。重新解压验证仍使用同一 Linux 的已有依赖，不能替代干净机器安装。
