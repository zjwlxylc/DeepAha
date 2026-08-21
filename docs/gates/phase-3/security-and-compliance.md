# Phase 3 安全、许可与范围检查

## 已实施边界

- 只使用官方证据等级与许可安全/CC0 合成 fixture；不提交受限原件。
- 高影响 Version/Event 必须绑定同一 Document 的 EvidenceRef；数据库复合外键执行该约束。
- Resolver 不访问 LLM、浏览器或 live 站点；弱/冲突证据进入 NEEDS_REVIEW。
- Phase 3 本地服务仅使用 `infra/compose.phase3.yaml`、55433/55001 与独立 project name。
- 测试凭据是 disposable 本地/CI 常量，不是外部 secret，也不授权 live 采集。

## 交付前扫描

2026-08-22 已实际复核 tracked artifact、secret pattern、Phase 2 live 标识/端口隔离和完整
diff：

- tracked `.env`、数据库、缓存、依赖目录、对象/data 目录规则零命中；
- AKIA 与私钥规则零命中；`Set-Cookie` 仅命中“不保存”设计文字和防泄漏测试；
- 数据库 URL 命中均为历史计划、测试断言或明确 disposable 的本地/CI 常量；
- Phase 3 compose/verifier/CI 对 55432、55000、`deepaha-phase2-live-gate` 的 scoped 扫描零命中。

当前结论：`LOCAL SCAN PASS`。精确候选 SHA `f5b89db…` 的 GitHub Actions run
32523434567 四个 jobs 均成功；Phase 2 closing commit 后仍需重做 diff/CI 复核。

本文件不是法律意见；Phase 3 没有面向公众发布、用户数据、招聘交易或 AI 内容输出。
