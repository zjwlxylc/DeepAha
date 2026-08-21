# Phase 0 工程基础 Gate

> Gate 状态：`OPEN`
> 本地验证基线：`3e55e855879bf65fbf66c2c9bb2127e9f9a73f96`
> 证据日期：2026-08-21

## 目标与范围

本 Gate 只验收 Phase 0 工程基础：根工程约束、FastAPI 最小后端、Next.js 最小 Web、统一本地验证入口与 GitHub Actions 工作流。数据库、采集、LLM、规则、用户系统和其他业务能力不在本次范围内。

## 结论

- 本地新鲜副本验收：`PASS`。根验证脚本退出码为 `0`。
- 远程持续集成：`BLOCKED`。当前仓库的 Git remote 数量为 `0`，无法推送或观察 GitHub Actions 的 `backend-quality` 与 `web-quality` 作业。
- 最终 Gate：`OPEN`。本地通过不能替代真实远程 CI 证据。

Phase 1 的进入条件尚未满足，本次工作没有进入 Phase 1。

## 已知风险与观察

1. 配置 GitHub 远程仓库、推送当前提交并取得两个 CI 作业成功结果后，才能复核是否把 Gate 改为 `CLOSED`。
2. pnpm 10.15.0 在安装时提示默认忽略 `esbuild`、`sharp`、`unrs-resolver` 的构建脚本；未批准额外脚本的情况下，组件测试、Lint、类型检查和 Next.js 生产构建均已实际通过。
3. Phase 0 按设计不制作正式 favicon。开发服务器浏览器检查中，浏览器对 `/favicon.ico` 的默认请求返回 404；页面没有加载原始 `设计/logo.png`，该观察不改变当前范围。

详细证据见 [验收结果](./acceptance-results.md)、[测试摘要](./test-summary.md) 和 [延期决策](./deferred-decisions.md)。
