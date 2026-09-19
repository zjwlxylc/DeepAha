# 来源资产工作台 Implementation Plan

> **For agentic workers:** Execute inline task-by-task with verification checkpoints; see the installed executing-plans workflow.

**Goal:** 让来源管理员用同一工作台安全检查和审核 GPT/WB 研究包，保存受控基线并导出不冒充系统回执的交接成果。
**Architecture:** 增量扩展原 v0.2.0；严格提交内核不放宽。研究适配器+持久化工作区+回环浏览器界面。
**Tech Stack:** Python 3.11+ standard library, HTML/CSS/JavaScript, unittest；旧可选FastAPI/Postgres依赖不改变。
**Spec:** docs/v0.3.0/DESIGN.md

## Global Constraints
原件不可覆盖；不调用生产库；不自动批准来源；不得将研究状态冒充系统状态；命名空间隔离；所有不确定项可见；人工上传与程序调用Codex入口均保留。

## Task 1 — 安全读取与规范审核
Files: research/ingest.py, normalize.py, audit.py; tests/test_research.py.
- [x] 写失败测试：ZIP路径穿越、大小写重名、重复JSON字段被拒绝；同一候选2版本归为1对象而不丢原文。
- [x] Run `python -m unittest tests.test_research -v`，确认缺少研究适配能力。
- [x] 实现 `load_inputs(paths, namespace='AUTO')`、`analyze(inputs)`；输出原件清单、48批兼容、候选版本、引用和附件问题。
- [x] 测试：保留hash路由、查询参数、命名空间；按SHA映射附件；分数缺失不当零。

## Task 2 — 基线与持久化审核
Files: research/baseline.py, workspace.py; tests/test_workspace.py.
- [x] 写 `create_controlled_baseline()` 不把state_complete改真、不删除缺口的失败测试。
- [x] 实现 `verify_state_chain()`、`create_controlled_baseline()`、`Workspace.create/get/decide/export`。
- [x] 并发编辑使用revision锁；导出ZIP包括每个原件与SHA；重新打开保留决定。
- [x] 用30轮与WB真实包生成同一审核报告，另外分别输出两侧统计，基线单独存档。

## Task 3 — 工作台与兼容入口
Files: workbench.py, web/index.html, app.js, style.css, cli.py, launchers; tests/test_workbench.py.
- [x] 写HTTP无令牌、错误Origin、未知路径、选择文件与导出的失败测试。
- [x] 实现`create_server()`回环服务器和浏览器四步骤；所有正文使用textContent，公开URL白名单。
- [x] 默认启动工作台；原 `gui` 命令与资料库获取保留；不静默创建生产连接。
- [x] 桌面/390px离线DOM与Application实测；浏览器HTTP因管理员策略阻断，单列为未验收，见VALIDATION。

## Task 4 — 反馈接口与交付
Files: docs/v0.3.0/FEEDBACK_PLAN.md, schemas, scripts/audit_assets.py, evidence/v0.3.0.
- [x] 按当前主仓真实接口规划分阶段回执：候选接收→来源映射→采集结果，未知值为null。
- [x] 回执导入只证明格式，未与实例核验时不可标“已验证生产反馈”。
- [x] 运行全套unittest与真实包回放；生成文件SHA和源码改动清单，核对ZIP可解压。
- [ ] 上传源码包、受控基线、审核成果到资料库，回读检查SHA；归档状态由最终外部ArchiveReceipt记录，不提前写PASS。

## 完成边界
本地功能/真实包离线回放已完成。主系统接入只交付方案；真实Windows、Codex账号、生产反馈认证未完成，不由上述勾选替代。独立子代理代码审查未执行。归档属于打包后的交付动作，以外部回执为准。
