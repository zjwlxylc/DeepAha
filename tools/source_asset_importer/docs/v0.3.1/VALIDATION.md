# v0.3.1 验证记录

验证日期：2026-09-13。范围：本次资料库获取与导出时间修正；不代表生产或用户账号验收。

## 已执行

| 项目 | 结果 | 证据 |
|---|---|---|
| 原v0.3.0回归基线 | 142项，141通过、1跳过 | 本次工作目录中的基线日志；旧证据仍保留 |
| 修正版全量unittest | **163项：162通过、1跳过、0失败** | evidence/v0.3.1/12_release_tests.log |
| JavaScript语法检查 | PASS | node --check deepaha_importer/web/app.js |
| Python编译检查 | PASS | python -m compileall -q deepaha_importer |
| 新增失败反例 → 修正通过 | 已记录 | 01_red/02_core_green、05_runtime_red/06_runtime_green、10/11_redaction日志 |
| 用户r58包CRC、清单和逻辑哈希 | PASS | user_export_audit.json |
| 58条事件回放及52项最终决定 | PASS | user_export_audit.json |
| WB原件在新旧版本的来源/问题对照 | 完全相同 | reanalysis_regression.json |
| 实际r58旧导出复用 | 原字节保持一致 | actual_r58_export_regression.json |
| 新导出时间与Schema | PASS；旧Schema兼容 | actual_r58_export_regression.json |
| 本环境实际缺少Codex的前置检查 | 正确返回CODEX_NOT_FOUND | real_environment_diagnostic.json |
| 合成Codex真实子进程 | 版本、参数、取消、错误分类通过 | 06_runtime_green.log |
| 独立真实回环HTTP | 会话令牌、跨域/Host、诊断下载/路径隔离通过 | 全量测试中test_workbench/test_library_http_patch |
| 离线DOM交互 | 163项测试之外的独立检查通过 | browser/dialog_validation.json、09_dom_final.log |

跳过项为需要单独环境变量和隔离PostgreSQL实例的旧内核测试，不是资料库测试“通过”。全套测试使用Xvfb提供Tk显示。少数较早诊断日志有旧SQLite ResourceWarning；最终记录未出现此告警，仍不据此宣称已经专项修复旧数据库资源生命周期。

## 浏览器验证准确范围

正常访问本机HTTP地址时，管理员策略返回ERR_BLOCKED_BY_ADMINISTRATOR；已停止这条浏览器导航验证，没有解除策略，也未搭代理绕过。该记录在browser/normal-navigation-result.json。

后续浏览器仅载入本地HTML/CSS/JS至about:blank，fetch/download/storage使用显式测试替身，直接调用本地应用方法，不发送网络请求。它证明模态弹窗内取消能够取得焦点和点击、重复按钮禁用、状态恢复、诊断下载动作、390px不横向溢出、手工文件入口保留；不能证明浏览器HTTP端到端、真实远端资料库或Windows实机。

r58画面来自用户交接包在隔离测试存储中重建的会话fixture，不是访问用户电脑数据库，亦不是新增“导入ZIP恢复原审批”的功能。

## 未执行/不能宣称

- 用户本机Codex的CLI版本、配置、登录、实际目录及原件权限尚未取得诊断；**真实资料库直连成功未验证**。
- 当前环境没有Codex CLI，模拟CLI/连接器仅用于协议与取消测试。
- 没有Windows实机测试、DeepAha生产接收、真实来源批准、WMA运行、事实发布或平台签名回执验证。
- 主项目比较只针对用户给出的ZIP快照，不代表当前GitHub HEAD/CI或线上状态。
- 本轮代码检查由同一助手结合回归测试进行，没有宣称独立外部审查员或独立子智能体验收。

## 本地复现

```text
python -m unittest discover -s tests -v
node --check deepaha_importer/web/app.js
python scripts/audit_review_export.py 用户交接包.zip audit-result.json
```

Linux无显示环境运行Tk测试需Xvfb；Windows使用正常桌面会话。Playwright/Chromium只为可选开发测试使用，不是日常工作台依赖。

交付ZIP构建时校验成员哈希和CRC；新目录解压后再次运行同一测试集，结果记录在源码包外的发布验证文件，避免把ZIP自身哈希嵌入自身形成循环。
