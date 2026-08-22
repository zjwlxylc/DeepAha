# Phase 3 安全、许可与范围检查

## 已实施边界

- 只使用官方证据等级与许可安全/CC0 合成 fixture；不提交受限原件。
- 高影响 Version/Event 必须绑定同一 Document 的 EvidenceRef；数据库复合外键执行该约束。
- Resolver 不访问 LLM、浏览器或 live 站点；弱/冲突证据进入 NEEDS_REVIEW。
- Phase 3 本地服务仅使用 `infra/compose.phase3.yaml`、55433/55001 与唯一 project name。
- 测试凭据是 disposable 本地/CI 常量，不是外部 secret，也不授权 live 采集。

## Engineering Gate 扫描

2026-08-22 在纳入 Phase 2 closing commit 后实际复核完整 Phase 3 diff、tracked artifacts、
secret patterns、fixture 许可和 Phase 2 live 隔离：

- tracked `.env`、数据库、缓存、依赖目录、构建目录、对象/data 目录：`0` 命中；
- AKIA 与私钥规则：`0` 文件命中；
- Phase 3 verifier/compose/CI 对 55432、55000、`deepaha-phase2-live-gate`：`0` 命中；
- Resolver fixture 明确标记 `synthetic: true` 与 `CC0-1.0 synthetic fixture`；
- Phase 3 verifier 仅创建并清理 `deepaha-phase3-$PID`，实际运行后 project/network 均移除。

当前结论：`ENGINEERING SCAN PASS`。本文件不是法律意见；Phase 3 没有面向公众发布、用户
数据、招聘交易或 AI 内容输出。Release Qualification 尚未开始，不能由本扫描推出生产安全。
